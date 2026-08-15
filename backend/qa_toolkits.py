# -*- coding: utf-8 -*-
"""QA 板块后端工具函数集 — 完全照搬独立视频质检工具的功能：

  - 文件夹自动检测（auto_detect_folders）
  - 文件一致性校验（check_consistency）
  - 项目名自动填充（auto_fill_project_name）
  - 字幕区域帧提取（extract_preview_frame）
  - 断点续检的 checkpoint 读写（load_checkpoint / save_checkpoint / clear_checkpoint）
  - HTML 报告生成（generate_report_html）
  - JSON 数据导出（generate_report_json）
  - 检测项选项（detection options）

这些函数被 enhanced_routes.py 中新增的路由直接调用，作为 Web 版质检 Tab 的后端支撑。
"""

import os
import sys
import re
import json
import time
import tempfile
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import detection

logger = logging.getLogger("qa_toolkits")

VIDEO_EXTS = ('.mp4', '.mov', '.mkv', '.avi', '.flv', '.wmv')
SRT_EXTS = ('.srt', '.ass', '.ssa', '.vtt')

# ============================================================
# 报告模板 CSS（直接从独立工具 report_template.py 复制，保证视觉一致）
# ============================================================
REPORT_CSS = r"""
  :root {
    --bg: #f7f8fa;
    --card: #ffffff;
    --text: #1f2937;
    --text2: #6b7280;
    --border: #e5e7eb;
    --primary: #3b82f6;
    --success: #22c55e;
    --warning: #f59e0b;
    --danger: #ef4444;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { color: var(--text); border-bottom: 3px solid var(--primary); padding-bottom: 12px; margin-bottom: 24px; }
  h2 { color: var(--text); margin-top: 32px; padding-left: 12px; border-left: 4px solid var(--primary); }
  .meta { color: var(--text2); font-size: 14px; margin-bottom: 16px; }
  .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); border-left: 4px solid var(--primary); }
  .stat-card.success { border-left-color: var(--success); }
  .stat-card.warning { border-left-color: var(--warning); }
  .stat-card.danger { border-left-color: var(--danger); }
  .stat-value { font-size: 28px; font-weight: 700; color: var(--text); }
  .stat-label { color: var(--text2); font-size: 13px; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; box-shadow: var(--shadow); margin-bottom: 24px; }
  thead { background: #f3f4f6; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; }
  th { font-weight: 600; color: var(--text); }
  td { color: var(--text); }
  tr:hover { background: #f9fafb; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .badge-success { background: #d1fae5; color: #065f46; }
  .badge-warning { background: #fef3c7; color: #92400e; }
  .badge-danger { background: #fee2e2; color: #991b1b; }
  .conclusion { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); border-left: 4px solid var(--success); padding: 16px 20px; border-radius: 8px; margin-bottom: 16px; }
  .conclusion.warning { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-left-color: var(--warning); }
  .conclusion.danger { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); border-left-color: var(--danger); }
  .conclusion strong { color: #064e3b; }
  .note { background: #eff6ff; border-left: 3px solid var(--primary); padding: 12px 16px; border-radius: 4px; margin: 12px 0; font-size: 14px; color: var(--text); }
  .video-num { font-family: monospace; font-weight: 600; }
  details { margin-bottom: 8px; }
  summary { cursor: pointer; padding: 10px 12px; background: #f9fafb; border-radius: 6px; font-weight: 500; }
  summary:hover { background: #f3f4f6; }
"""


# ============================================================
# 1. 文件夹自动检测（完全照搬 video_qa_tool.py auto_detect_folders）
# ============================================================
def auto_detect_folders(base):
    """扫描项目目录，返回完整的文件夹布局与数量统计。

    返回:
        {
          "available_folders": ["成片","无字幕版",...],   # 所有含视频/srt的文件夹
          "cp_folder": "成片",                            # 识别到的成片文件夹
          "cp_match_auto": True,                          # 是否是关键字命中的
          "hardsub_folders": ["成片", "无字幕版"],         # 有视频的候选版本
          "hardsub_vars_default": {"成片": True, "无字幕版": True},  # 默认勾选
          "srt_folder": "字幕文件" 或 None,
          "srt_count": 3,
          "file_counts": {"成片": 10, "无字幕版": 10},
          "consistent": True,
          "first_video_path": "D:/项目X/成片/01.mp4" 或 None,
          "first_video_info": {width, height, fps, duration, codec} 或 None,
        }
    """
    base = os.path.abspath(base)
    out = {
        "available_folders": [],
        "cp_folder": None,
        "cp_match_auto": False,
        "hardsub_folders": [],
        "hardsub_vars_default": {},
        "srt_folder": None,
        "srt_count": 0,
        "file_counts": {},
        "consistent": False,
        "first_video_path": None,
        "first_video_info": None,
    }
    if not base or not os.path.isdir(base):
        return out

    try:
        entries = sorted(os.listdir(base))
    except OSError:
        return out

    available = []
    for name in entries:
        full = os.path.join(base, name)
        if not os.path.isdir(full):
            continue
        try:
            files = os.listdir(full)
        except OSError:
            continue
        if any(f.endswith(VIDEO_EXTS) for f in files) or any(f.endswith('.srt') for f in files):
            available.append(name)
    out["available_folders"] = available

    cp_match = srt_match = None
    hardsub_matches = []

    for f in available:
        fl = f.lower()
        full = os.path.join(base, f)
        try:
            files = os.listdir(full)
        except OSError:
            continue
        has_video = any(x.endswith(VIDEO_EXTS) for x in files)
        has_srt = any(x.endswith('.srt') for x in files)

        if has_srt or '字幕文件' in f or fl.startswith('3') or 'srt' in fl:
            srt_match = f
            continue
        if '成片' in f or fl.startswith('00') or 'final' in fl:
            cp_match = f
            continue
        if '无字幕' in f:
            hardsub_matches.append(f)
            continue

    if not cp_match:
        for f in available:
            full = os.path.join(base, f)
            try:
                if any(x.endswith('.mp4') for x in os.listdir(full)):
                    cp_match = f
                    break
            except OSError:
                continue
    else:
        out["cp_match_auto"] = True

    if not hardsub_matches:
        for f in available:
            if f != cp_match and f != srt_match:
                full = os.path.join(base, f)
                try:
                    if any(x.endswith(VIDEO_EXTS) for x in os.listdir(full)):
                        hardsub_matches.append(f)
                except OSError:
                    continue

    out["cp_folder"] = cp_match
    out["srt_folder"] = srt_match

    # srt 数量
    if srt_match:
        srt_dir = os.path.join(base, srt_match)
        try:
            out["srt_count"] = len([f for f in os.listdir(srt_dir) if f.endswith(SRT_EXTS)])
        except OSError:
            pass

    # 文件数量
    all_video_folders = []
    if cp_match:
        all_video_folders.append(cp_match)
    for f in hardsub_matches:
        if f not in all_video_folders:
            all_video_folders.append(f)

    file_counts = {}
    for folder in all_video_folders:
        try:
            n = len([f for f in os.listdir(os.path.join(base, folder))
                     if f.endswith(VIDEO_EXTS)])
        except OSError:
            n = 0
        file_counts[folder] = n

    out["hardsub_folders"] = hardsub_matches
    out["hardsub_vars_default"] = {f: True for f in hardsub_matches}
    if cp_match:
        out["hardsub_vars_default"][cp_match] = True
    out["file_counts"] = file_counts

    all_vals = list(file_counts.values()) + ([out["srt_count"]] if srt_match else [])
    out["consistent"] = (len(set(all_vals)) == 1) if all_vals else False

    # 第一个视频信息（用于字幕区域框选预览）
    if cp_match:
        cp_dir = os.path.join(base, cp_match)
        try:
            vfiles = sorted(
                [f for f in os.listdir(cp_dir) if f.endswith(VIDEO_EXTS)],
                key=detection.natural_sort_key
            )
        except OSError:
            vfiles = []
        if vfiles:
            first = os.path.join(cp_dir, vfiles[0])
            out["first_video_path"] = first
            info = detection.get_video_info(first)
            if info:
                out["first_video_info"] = {
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "fps": info.get("fps"),
                    "duration": info.get("duration"),
                    "codec": info.get("codec"),
                }

    return out


def auto_fill_project_name(base):
    """从目录路径智能提取项目名（与独立工具 _auto_fill_project_name 一致）。"""
    base_name = os.path.basename(os.path.abspath(base))
    if '交付' in base_name or base_name.startswith('000'):
        parent = os.path.basename(os.path.dirname(os.path.abspath(base)))
        if parent:
            return parent
    return base_name


# ============================================================
# 2. 字幕区域帧提取 + Pillow JPEG 编码（为 Web 框选 UI 提供预览图）
# ============================================================
def extract_preview_frame(video_path, timestamp_fraction=0.25):
    """提取视频指定时刻的一帧，返回 (rgb_ndarray, width, height)。

    timestamp_fraction=0.25 对应独立工具 25% 时刻（避开片头黑屏）。
    """
    info = detection.get_video_info(video_path)
    if not info:
        return None, 0, 0
    duration = info.get('duration', 0) or 10
    ts = min(duration * timestamp_fraction, max(duration - 1, 0))
    frame = detection._extract_full_rgb_frame(
        video_path, ts,
        width=info.get('width'),
        height=info.get('height')
    )
    if frame is None:
        return None, 0, 0
    h, w = frame.shape[:2]
    return frame, w, h


def encode_frame_to_jpeg(frame, quality=85, max_width=None):
    """把 RGB numpy 数组编码成 JPEG 字节串（供 Web 端 <img src="data:image/jpeg;base64,...">）。

    max_width 不为 None 时等比缩放（加速前端框选预览）。
    """
    try:
        import cv2
    except ImportError:
        return None
    h, w = frame.shape[:2]
    if max_width and w > max_width:
        scale = max_width / w
        new_h, new_w = max(1, int(h * scale)), max_width
        out = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        out = frame
    # RGB -> BGR (cv2.imencode 期望 BGR)
    bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode('.jpg', bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return buf.tobytes()


# ============================================================
# 3. Checkpoint（断点续检）读写
# ============================================================
def checkpoint_path(project_path):
    return os.path.join(os.path.abspath(project_path), '.qa_checkpoint.json')


def load_checkpoint(project_path, opts=None):
    """加载断点，返回 {video_name_without_ext: result_dict}。

    如果 opts 与 checkpoint 中保存的 options 不一致，丢弃 checkpoint（保证结果正确性）。
    """
    path = checkpoint_path(project_path)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # options 不匹配 → 丢弃
    if opts is not None and data.get('options') and not _opts_match(data.get('options'), opts):
        logger.info("断点 options 不匹配，丢弃断点: %s", path)
        return {}
    results = data.get('results')
    if not isinstance(results, dict):
        return {}
    return results


def save_checkpoint(project_path, results, opts=None):
    """把 {video_name: result_dict} 写入 checkpoint。"""
    path = checkpoint_path(project_path)
    payload = {
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'options': _sanitize_opts(opts) if opts else None,
        'results': {r.get('video', ''): r for r in results},
    }
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        logger.error("保存 checkpoint 失败: %s", e)
        return False


def clear_checkpoint(project_path):
    path = checkpoint_path(project_path)
    try:
        if os.path.isfile(path):
            os.remove(path)
            return True
    except OSError as e:
        logger.error("清除 checkpoint 失败: %s", e)
    return False


def _sanitize_opts(opts):
    """只保留与检测结果相关的关键字段，用于对比 checkpoint 一致性。"""
    return {
        k: opts.get(k) for k in (
            'cp_folder', 'hardsub_folders', 'srt_folder',
            'opt_blackframes', 'opt_hardsubs', 'opt_duration',
            'sub_region',
        ) if k in opts
    }


def _opts_match(saved, current):
    return _sanitize_opts(saved) == _sanitize_opts(current)


# ============================================================
# 4. HTML 报告生成（完全照搬 video_qa_tool._generate_report 逻辑）
# ============================================================
def generate_report_html(project_path, project_name, results, total,
                         extra_data=None, workers=4, output_path=None):
    """生成完整 HTML 报告。返回报告的最终保存路径。"""
    if not output_path:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"质检报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )

    extra_data = extra_data or {}
    file_counts = extra_data.get('file_counts', {})
    srt_count = extra_data.get('srt_count', 0)
    consistent = extra_data.get('consistent', True)
    folder_info = extra_data.get('folder_info', {})
    srt_folder = extra_data.get('srt_folder', '')
    cp_folder = extra_data.get('cp_folder') or folder_info.get('cp_folder', '')

    all_video_folders = folder_info.get('all_video_folders') or ([cp_folder] if cp_folder else [])
    if not all_video_folders:
        # 兜底：根据 results 推
        all_video_folders = sorted({
            f for r in results for f in (r.get('hard_sub') or {}).keys()
        })
        if cp_folder and cp_folder not in all_video_folders:
            all_video_folders.insert(0, cp_folder)

    width = folder_info.get('width') or '?'
    height = folder_info.get('height') or '?'
    fps = folder_info.get('fps') or '?'
    sub_y = folder_info.get('sub_y') if folder_info.get('sub_y') is not None else '?'
    sub_h = folder_info.get('sub_h') if folder_info.get('sub_h') is not None else 0

    pass_n = sum(1 for r in results if r.get('status') == 'pass')
    warn_n = sum(1 for r in results if r.get('status') == 'warn')
    fail_n = sum(1 for r in results if r.get('status') == 'fail')

    # 硬字幕按版本统计
    hs_total = sum(1 for r in results if r.get('hard_sub'))
    hs_pass = sum(
        1 for r in results if r.get('hard_sub')
        and all(not v.get('has_hardsub') for v in (r.get('hard_sub') or {}).values())
    )
    hs_fail = hs_total - hs_pass

    hs_by_version = {}  # folder -> {pass, fail, data}
    for r in results:
        for folder, hs in (r.get('hard_sub') or {}).items():
            if folder not in hs_by_version:
                hs_by_version[folder] = {'pass': 0, 'fail': 0, 'data': []}
            has = bool(hs.get('has_hardsub', False))
            is_cp = (folder == cp_folder)
            ok = has if is_cp else not has
            if ok:
                hs_by_version[folder]['pass'] += 1
            else:
                hs_by_version[folder]['fail'] += 1
            hs_by_version[folder]['data'].append(
                (r.get('video', ''), hs.get('avg_density', 0),
                 hs.get('max_density', 0), has, is_cp)
            )

    # 黑帧
    bf_videos = [r for r in results if r.get('black_frames', {}).get(cp_folder)]
    bf_count = len(bf_videos)

    bf_consistent = True
    for r in bf_videos:
        bfs = r.get('black_frames', {})
        versions_with_bf = [f for f in all_video_folders if bfs.get(f)]
        if len(versions_with_bf) < len(all_video_folders):
            bf_consistent = False
            break

    durations = [r.get('duration', 0) for r in results if r.get('duration', 0) > 0]
    dur_min = min(durations) if durations else 0
    dur_max = max(durations) if durations else 0

    # === 文件清单核对 HTML ===
    file_rows = ""
    for folder in all_video_folders:
        count = file_counts.get(folder, 0)
        file_rows += (
            f"<tr><td>{folder}/</td><td>{count}</td><td>.mp4</td>"
            f"<td>{width}x{height}</td><td>{fps}fps</td>"
            f"<td>{dur_min:.1f}s ~ {dur_max:.1f}s</td></tr>\n"
        )
    if srt_folder:
        file_rows += (
            f"<tr><td>{srt_folder}/</td><td>{srt_count}</td><td>.srt</td>"
            f"<td colspan='3'>与成片一一对应</td></tr>\n"
        )

    # === 黑帧表 HTML ===
    bf_rows = ""
    for r in sorted(bf_videos, key=lambda x: detection.natural_sort_key(x.get('video', ''))):
        bfs_all = r.get('black_frames', {})
        first_bf = bfs_all.get(cp_folder, [])
        total_dur = sum(b.get('duration', 0) for b in first_bf)
        per_version_cells = []
        for folder in all_video_folders:
            bf_folder = bfs_all.get(folder, [])
            if bf_folder:
                pos = ", ".join([f"{b['start']:.1f}-{b['end']:.1f}s" for b in bf_folder[:2]])
                if len(bf_folder) > 2:
                    pos += "..."
                per_version_cells.append(f"{folder}: {pos}")
            else:
                per_version_cells.append(f"{folder}: —")
        per_version_html = '<br>'.join(per_version_cells)
        badge_cls = 'warning' if bf_consistent else 'danger'
        badge = (f'<span class="badge badge-{badge_cls}">'
                 f'{"结尾黑帧·场景转场" if bf_consistent else "跨版本不一致·需检查"}</span>')
        bf_rows += (
            f'<tr><td class="video-num">{r["video"]}</td><td>{len(first_bf)}</td>'
            f'<td>{total_dur:.2f}s</td>'
            f'<td style="font-size:13px; line-height:1.7;">{per_version_html}</td>'
            f'<td>{badge}</td></tr>\n'
        )

    # === 问题清单 ===
    issues = {
        'hardsub_cp_missing': [],
        'hardsub_version_present': [],
        'black_frame': [],
        'count_mismatch': [],
        'duration_mismatch': [],
        'fps_mismatch': [],
    }
    for r in results:
        vname = r.get('video', '')
        for folder, hs in (r.get('hard_sub') or {}).items():
            has_hs = bool(hs.get('has_hardsub', False))
            is_cp = (folder == cp_folder)
            if is_cp and not has_hs:
                issues['hardsub_cp_missing'].append((vname, folder))
            elif not is_cp and has_hs:
                issues['hardsub_version_present'].append((vname, folder))
        dc = r.get('duration_check') or {}
        if dc.get('status') == 'fail':
            issues['duration_mismatch'].append(vname)
        fc = r.get('fps_check') or {}
        if fc.get('status') == 'fail':
            issues['fps_mismatch'].append(vname)
    for r in sorted(bf_videos, key=lambda x: detection.natural_sort_key(x.get('video', ''))):
        vname = r.get('video', '')
        bfs_all = r.get('black_frames', {})
        versions_with_bf = [f for f in all_video_folders if bfs_all.get(f)]
        is_c = len(versions_with_bf) == len(all_video_folders)
        label = ("场景转场（各版本一致）" if is_c
                 else f"仅{','.join(versions_with_bf)}有（需检查）")
        issues['black_frame'].append((vname, label))
    if not consistent:
        for folder in all_video_folders:
            cnt = file_counts.get(folder, 0)
            if cnt != total:
                issues['count_mismatch'].append(f"{folder}: {cnt}个（期望{total}）")

    issue_html = ""
    has_any = any(len(v) > 0 for v in issues.values())
    if has_any:
        issue_html += (
            '<div class="issues-box" style="background:#fff7ed; border-left:4px solid var(--warning); '
            'border-radius:8px; padding:16px 20px; margin-bottom:24px;">\n'
            '<h2 style="margin-top:0; border-left:none; padding-left:0; color:#92400e;">🚨 问题清单（必看）</h2>\n'
        )
        cats = [
            ('hardsub_cp_missing', '成片缺硬字幕（需要字幕但没有）', 'danger'),
            ('hardsub_version_present', '无字幕版本有硬字幕（不该有但有）', 'danger'),
            ('black_frame', '结尾黑帧（按版本列出）', 'warning'),
            ('duration_mismatch', '时长跨版本不一致', 'danger'),
            ('fps_mismatch', '帧率异常', 'danger'),
            ('count_mismatch', '文件数量不一致', 'danger'),
        ]
        for cat_key, title, cls in cats:
            items = issues.get(cat_key, [])
            if not items:
                continue
            badge_cls = 'badge-danger' if cls == 'danger' else 'badge-warning'
            issue_html += (
                f'<h3 style="margin:16px 0 8px; font-size:16px;">• {title} '
                f'<span class="badge {badge_cls}">{len(items)}项</span></h3>\n'
                '<ul style="margin:4px 0; padding-left:24px; font-size:14px; line-height:1.9;">\n'
            )
            if cat_key == 'hardsub_cp_missing':
                for vname, folder in items:
                    issue_html += f'<li>第 <strong>{vname}</strong> 集（版本：<code>{folder}</code>）— 缺少硬字幕，请重新烧录字幕</li>\n'
            elif cat_key == 'hardsub_version_present':
                for vname, folder in items:
                    issue_html += f'<li>第 <strong>{vname}</strong> 集（版本：<code>{folder}</code>）— 检测到硬字幕，请确认导出是否忘记关掉字幕轨</li>\n'
            elif cat_key == 'black_frame':
                for vname, label in items:
                    issue_html += f'<li>第 <strong>{vname}</strong> 集 — {label}</li>\n'
            elif cat_key == 'duration_mismatch':
                for vname in items:
                    r = next((x for x in results if x.get('video') == vname), None)
                    if r and r.get('duration_check'):
                        durs = (r['duration_check'] or {}).get('durations', {})
                        dur_s = ' ｜ '.join([f"{f}:{d:.2f}s" for f, d in durs.items()])
                        issue_html += f'<li>第 <strong>{vname}</strong> 集 — {dur_s}</li>\n'
                    else:
                        issue_html += f'<li>第 <strong>{vname}</strong> 集 — 时长不一致</li>\n'
            elif cat_key == 'fps_mismatch':
                for vname in items:
                    r = next((x for x in results if x.get('video') == vname), None)
                    if r and r.get('fps_check'):
                        fps_map = (r['fps_check'] or {}).get('fps_values', {})
                        fps_s = ' ｜ '.join([f"{f}:{v:.1f}fps" for f, v in fps_map.items()])
                        issue_html += f'<li>第 <strong>{vname}</strong> 集 — {fps_s}</li>\n'
                    else:
                        issue_html += f'<li>第 <strong>{vname}</strong> 集 — 帧率异常</li>\n'
            elif cat_key == 'count_mismatch':
                for d in items:
                    issue_html += f'<li>{d}</li>\n'
            issue_html += '</ul>\n'
        issue_html += '</div>\n'
    else:
        issue_html = (
            '<div class="issues-box" style="background:#ecfdf5; border-left:4px solid var(--success); '
            'border-radius:8px; padding:16px 20px; margin-bottom:24px;">\n'
            '<h2 style="margin-top:0; border-left:none; padding-left:0; color:#065f46;">✅ 没有发现问题</h2>\n'
            '<p style="color:#065f46; margin:0;">所有版本的所有视频均通过检测。</p>\n</div>\n'
        )

    # === 按版本硬字幕表格 ===
    hs_sec_html = ""
    if hs_by_version:
        for folder in all_video_folders:
            vd = hs_by_version.get(folder)
            if not vd:
                continue
            v_pass, v_fail = vd['pass'], vd['fail']
            v_total = v_pass + v_fail
            is_cp = (folder == cp_folder)
            cls2 = 'success' if v_fail == 0 else 'danger'
            if is_cp:
                label = '有硬字幕（正常）' if v_fail == 0 else f'{v_fail}个缺硬字幕'
            else:
                label = '无硬字幕（正常）' if v_fail == 0 else f'{v_fail}个有硬字幕'
            hs_sec_html += (
                f'<h3 style="margin-top:20px;">{folder} '
                f'<span class="badge badge-{cls2}">{v_pass}/{v_total} {label}</span></h3>\n'
            )
            sorted_data = sorted(vd['data'], key=lambda x: -x[1])
            if v_fail > 0:
                show = [d for d in sorted_data if not (d[4] == is_cp and d[3] == is_cp)][:10]
                if len(show) < 5:
                    show = sorted_data[:10]
            else:
                show = sorted_data[:5]
            hs_sec_html += (
                '<table>\n<thead><tr><th>视频</th><th>边缘密度</th>'
                '<th>最大密度</th><th>判定</th></tr></thead>\n<tbody>\n'
            )
            for vname, avg_d, max_d, has_hs, is_cp_v in show:
                if is_cp_v:
                    if has_hs:
                        badge = '<span class="badge badge-success">有硬字幕（正常）</span>'
                    elif avg_d > 1.0:
                        badge = '<span class="badge badge-warning">边缘异常</span>'
                    else:
                        badge = '<span class="badge badge-danger">缺硬字幕</span>'
                else:
                    if has_hs:
                        badge = '<span class="badge badge-danger">有硬字幕（异常）</span>'
                    elif avg_d > 1.0:
                        badge = '<span class="badge badge-warning">轻微异常</span>'
                    else:
                        badge = '<span class="badge badge-success">无硬字幕（正常）</span>'
                hs_sec_html += (
                    f'<tr><td class="video-num">{vname}</td>'
                    f'<td>{avg_d:.2f}%</td><td>{max_d:.2f}%</td><td>{badge}</td></tr>\n'
                )
            hs_sec_html += '  </tbody>\n</table>\n'
    else:
        hs_sec_html = '<p style="color:var(--text2); font-size:14px;">未检测硬字幕（未选择检测选项）。</p>'

    has_fail = fail_n > 0 or not consistent
    has_warn = warn_n > 0
    if has_fail:
        conclusion_cls = 'danger'
        conclusion_text = '✗ 质检结论：有失败项'
    elif has_warn:
        conclusion_cls = 'warning'
        conclusion_text = '⚠ 质检结论：有警告项'
    else:
        conclusion_cls = ''
        conclusion_text = '✅ 质检结论：通过'

    conclusion_details = []
    if hs_by_version:
        for folder in all_video_folders:
            vd = hs_by_version.get(folder)
            if not vd:
                continue
            vp, vf = vd['pass'], vd['fail']
            vt = vp + vf
            is_cp = (folder == cp_folder)
            if is_cp:
                if vf > 0:
                    conclusion_details.append(f"- {folder}：{vp}/{vt} 有硬字幕，{vf}个缺硬字幕（需检查）")
                else:
                    conclusion_details.append(f"- {folder}：{vp}/{vt} 全部有硬字幕（正常）")
            else:
                if vf > 0:
                    conclusion_details.append(f"- {folder}：{vp}/{vt} 无硬字幕，{vf}个有硬字幕（需检查）")
                else:
                    conclusion_details.append(f"- {folder}：{vp}/{vt} 全部无硬字幕（正常）")
    if bf_count:
        c_str = "一致" if bf_consistent else "不一致"
        conclusion_details.append(
            f"- 结尾黑帧：{bf_count}个视频存在黑帧，各版本位置{c_str}"
            + ("，属于源文件固有特征（场景转场）" if bf_consistent else "，需检查")
        )
    conclusion_details.append(
        f"- 文件数量：{'一致' if consistent else '不一致，请检查'}"
        + (f"（{' / '.join(f'{k}={v}' for k, v in file_counts.items())}"
           + (f' / 字幕={srt_count}' if srt_folder else '') + '）' if not consistent else '')
    )

    END_CHECK_SECONDS = getattr(detection, 'END_CHECK_SECONDS', 5.0)
    BLACK_FRAME_PIX_TH = getattr(detection, 'BLACK_FRAME_PIX_TH', 0.10)
    BLACK_FRAME_DUR = getattr(detection, 'BLACK_FRAME_DUR', 0.08)
    HARD_SUB_SAMPLE_FRAMES = getattr(detection, 'HARD_SUB_SAMPLE_FRAMES', 8)
    EDGE_DENSITY_HIGH = getattr(detection, 'EDGE_DENSITY_HIGH', 2.5)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{project_name} — 视频质检报告</title>
<style>
{REPORT_CSS}
</style>
</head>
<body>
<div class="container">
<h1>{project_name} — 视频质检报告</h1>
<p class="meta">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 视频总数：{total} | 检测版本：{', '.join(all_video_folders) if all_video_folders else '—'} | 并行线程：{workers}</p>

<div class="summary">
  <div class="stat-card {'warning' if bf_count else 'success'}">
    <div class="stat-value">{bf_count}</div>
    <div class="stat-label">结尾黑帧{'（场景转场）' if bf_consistent else '（需检查）'}</div>
  </div>
  <div class="stat-card {'success' if hs_fail == 0 else 'danger'}">
    <div class="stat-value">{hs_pass}/{hs_total if hs_total else total}</div>
    <div class="stat-label">硬字幕检测（各版本）</div>
  </div>
  <div class="stat-card {'success' if consistent else 'danger'}">
    <div class="stat-value">{'一致' if consistent else '不一致'}</div>
    <div class="stat-label">文件数量一致性</div>
  </div>
  <div class="stat-card {'success' if pass_n == total else ('warning' if fail_n == 0 else 'danger')}">
    <div class="stat-value">{pass_n}/{total}</div>
    <div class="stat-label">通过 / 警告 {warn_n} / 失败 {fail_n}</div>
  </div>
</div>

{issue_html}

<div class="conclusion {conclusion_cls}">
  <strong>{conclusion_text}</strong><br>
  {'<br>'.join(conclusion_details)}
</div>

<h2>一、文件清单核对</h2>
<table>
  <thead><tr><th>目录</th><th>文件数</th><th>格式</th><th>分辨率</th><th>帧率</th><th>时长范围</th></tr></thead>
  <tbody>
{file_rows}  </tbody>
</table>

<h2>二、结尾黑帧检测</h2>
<div class="note">
  仅检测视频结尾 {END_CHECK_SECONDS} 秒，使用 ffmpeg <code>blackdetect</code> 滤镜，阈值：亮度&lt;{BLACK_FRAME_PIX_TH}，持续&gt;{BLACK_FRAME_DUR}秒。
  {'检测到' + str(bf_count) + '个视频结尾存在黑帧，各版本黑帧位置' + ('一致，属于源文件固有特征（场景转场），非编码问题。' if bf_consistent else '不一致，需进一步检查。') if bf_count else '未检测到结尾黑帧。'}
</div>
{f'''<table>
  <thead><tr><th>视频</th><th>黑帧段数</th><th>总时长</th><th>位置（秒）</th><th>判定</th></tr></thead>
  <tbody>
{bf_rows}  </tbody>
</table>''' if bf_count else ''}

<h2>三、硬字幕检测（各版本对比）</h2>
<div class="note">
  对所有版本在字幕区域（Y={sub_y}~{sub_y + sub_h if isinstance(sub_y, int) else '?'}）采样 {HARD_SUB_SAMPLE_FRAMES} 帧计算平均边缘密度。正常无字幕视频该值应&lt;1.0%；含硬字幕通常&gt;{EDGE_DENSITY_HIGH}%。以下按版本分别列出检测结果。
</div>
{hs_sec_html}

<h2>四、检测结果总表</h2>
<table>
  <thead><tr><th>视频</th><th>结尾黑帧</th><th>硬字幕（各版本）</th><th>状态</th><th>详情</th></tr></thead>
  <tbody>
"""
    for r in results:
        status_cls = {'pass': 'badge-success', 'warn': 'badge-warning', 'fail': 'badge-danger'}.get(
            r.get('status', 'pass'), 'badge-success')
        status_text = {'pass': '✓ 通过', 'warn': '⚠ 警告', 'fail': '✗ 失败'}.get(
            r.get('status', 'pass'), '—')
        cp_bf = (r.get('black_frames') or {}).get(cp_folder, [])
        bf = f"{len(cp_bf)}段" if cp_bf else "—"
        hs_parts = []
        if r.get('hard_sub'):
            for folder, hs in r['hard_sub'].items():
                has_hs = bool(hs.get('has_hardsub', False))
                is_cp = (folder == cp_folder)
                ok = has_hs if is_cp else not has_hs
                expect = "（应有字幕）" if is_cp else "（应无字幕）"
                b = (f'<span style="color:var(--success); font-weight:600;">✓ 正常</span>'
                     if ok else
                     f'<span style="color:var(--danger); font-weight:700;">✗ 异常</span>')
                hs_parts.append(
                    f'<div style="padding:3px 0;"><code style="background:#f3f4f6; padding:1px 6px; '
                    f'border-radius:4px; font-size:12px;">{folder}</code>{expect} → {b}</div>'
                )
        hs = "".join(hs_parts) if hs_parts else "—"
        html += (
            f'<tr><td class="video-num">{r.get("video", "")}</td><td>{bf}</td>'
            f'<td style="font-size:13px;">{hs}</td>'
            f'<td><span class="badge {status_cls}">{status_text}</span></td>'
            f'<td>{r.get("details", "")}</td></tr>\n'
        )

    html += f"""  </tbody>
</table>
</div>
</body>
</html>
"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info("HTML 报告已生成: %s", output_path)
    except OSError as e:
        logger.error("写 HTML 报告失败: %s", e)
        return None
    return output_path


def generate_report_json(project_path, project_name, results, extra_data=None):
    """以独立工具 export_json 完全一致的格式生成 JSON（dict），不写入文件。"""
    extra_data = extra_data or {}
    return {
        'project': project_path,
        'project_name': project_name,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'total': len(results),
        'file_counts': extra_data.get('file_counts', {}),
        'srt_count': extra_data.get('srt_count', 0),
        'consistent': extra_data.get('consistent', True),
        'folder_info': extra_data.get('folder_info', {}),
        'results': results,
    }
