# -*- coding: utf-8 -*-
"""视频质检工具 — 检测函数模块（纯函数，无 UI 依赖）
所有检测逻辑的唯一来源（single source of truth）。
桌面端 (video_qa_tool.py) 和 Web 端 (api.py) 均从此模块 import。
"""

import os
import sys
import json
import re
import time
import subprocess
import threading
import tempfile
import traceback as _traceback
from utils import decode_output
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import cv2

# ============================================================
# 配置常量 — 全项目唯一定义处
# ============================================================
BLACK_FRAME_DUR = 0.08
BLACK_FRAME_PIX_TH = 0.10
EDGE_DENSITY_HIGH = 2.5
EDGE_DENSITY_HIGH_ABSOLUTE = 3.5
END_CHECK_SECONDS = 5.0
HARD_SUB_SAMPLE_FRAMES = 8

DURATION_TOLERANCE = 0.5        # 时长一致性容差（秒）
START_CHECK_SECONDS = 5.0       # 开头黑帧检测秒数
# 字幕区域比例
SUB_Y_RATIO_START = 0.68
SUB_Y_RATIO_END = 0.83

SSIM_THRESHOLD = 0.95           # SSIM 低于此值视为画质差异
PSNR_THRESHOLD = 35.0           # PSNR 低于此值视为画质劣化

VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv')

# Windows: 防止 subprocess 调用时控制台窗口闪现
SUBPROCESS_FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _ffmpeg_cmd():
    """返回 ffmpeg 可执行路径：优先 exe 同目录，其次 PATH"""
    if getattr(sys, 'frozen', False):
        p = os.path.join(os.path.dirname(sys.executable), 'ffmpeg.exe')
        if os.path.isfile(p):
            return p
    return 'ffmpeg'


def _ffprobe_cmd():
    """返回 ffprobe 可执行路径：优先 exe 同目录，其次 PATH"""
    if getattr(sys, 'frozen', False):
        p = os.path.join(os.path.dirname(sys.executable), 'ffprobe.exe')
        if os.path.isfile(p):
            return p
    return 'ffprobe'


def _log_error(where):
    """将异常 traceback 写入日志文件（自动轮转：单文件 10MB，保留最近 3 个）"""
    try:
        log_dir = Path.home() / "视频质检工具"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "error.log"
        # 日志轮转：超过 10MB 时重命名
        if log_file.exists() and log_file.stat().st_size > 10 * 1024 * 1024:
            for i in range(2, 0, -1):
                old = log_file.with_suffix(f'.log.{i}')
                new = log_file.with_suffix(f'.log.{i + 1}')
                if old.exists():
                    old.rename(new)
            log_file.rename(log_file.with_suffix('.log.1'))
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(f"[{datetime.now().isoformat()}] {where}\n")
            _traceback.print_exc(file=lf)
            lf.write("\n")
    except Exception:
        pass


def get_video_info(video_path):
    try:
        result = subprocess.run(
            [_ffprobe_cmd(), '-v', 'quiet', '-print_format', 'json',
             '-show_streams', '-show_format', str(video_path)],
            capture_output=True, timeout=30, creationflags=SUBPROCESS_FLAGS
        )
        if result.returncode != 0 or not result.stdout:
            return None
        data = json.loads(decode_output(result.stdout))
        streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video']
        if not streams:
            return None
        s = streams[0]
        fps_str = s.get('r_frame_rate', '24/1')
        try:
            num, den = fps_str.split('/')
            fps = float(num) / float(den) if float(den) != 0 else 24.0
        except Exception:
            fps = 24.0
        return {
            'width': int(s['width']),
            'height': int(s['height']),
            'duration': float(data.get('format', {}).get('duration', 0)),
            'fps': round(fps, 2),
            'codec': s.get('codec_name', 'unknown'),
        }
    except Exception:
        _log_error(f"get_video_info: {video_path}")
        return None


def get_video_duration(video_path):
    """轻量获取单个视频时长（仅查询 duration，速度快）"""
    try:
        result = subprocess.run(
            [_ffprobe_cmd(), '-v', 'error', '-show_entries',
             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
             str(video_path)],
            capture_output=True, timeout=15, creationflags=SUBPROCESS_FLAGS
        )
        if result.returncode == 0 and result.stdout:
            return float(decode_output(result.stdout).strip())
    except Exception:
        pass
    return 0.0


def detect_ending_black_frames(video_path, duration, check_seconds=END_CHECK_SECONDS):
    start = max(0, duration - check_seconds)
    try:
        result = subprocess.run(
            [_ffmpeg_cmd(), '-ss', str(start), '-i', str(video_path),
             '-vf', f'blackdetect=d={BLACK_FRAME_DUR}:pix_th={BLACK_FRAME_PIX_TH}',
             '-an', '-f', 'null', '-'],
            capture_output=True, timeout=30, creationflags=SUBPROCESS_FLAGS
        )
        output = decode_output(result.stderr)
        frames = []
        for line in output.split('\n'):
            if 'black_start' in line:
                m = re.search(r'black_start:(\S+)\s+black_end:(\S+)\s+black_duration:(\S+)', line)
                if m:
                    frames.append({
                        'start': round(float(m.group(1)) + start, 2),
                        'end': round(float(m.group(2)) + start, 2),
                        'duration': round(float(m.group(3)), 3)
                    })
        return frames
    except Exception:
        _log_error(f"detect_ending_black_frames: {video_path}")
        return []


def _extract_frame_opencv(video_path, timestamp, want_rgb=False):
    """OpenCV VideoCapture 帧提取：单次打开容器 + seek + 读帧。
    失败返回 None（调用方应 fallback 到 ffmpeg）。
    相比 subprocess ffmpeg：省掉进程创建 + 容器重开，从 ~200ms/帧 → ~5ms/帧。
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_POS_MSEC, float(timestamp) * 1000.0)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None or frame.size == 0:
            return None
        if want_rgb:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    except Exception:
        return None


def extract_gray_frame(video_path, timestamp, width, height, crop_y=None, crop_h=None):
    """提取灰度帧。

    优先走 OpenCV VideoCapture（~5ms/帧），失败 fallback 到 ffmpeg。
    width/height 必须是视频的**完整尺寸**。如需裁剪，通过 crop_y/crop_h 参数。
    """
    frame = _extract_frame_opencv(video_path, timestamp, want_rgb=False)
    if frame is not None:
        full_h, full_w = frame.shape[:2]
        # 尺寸校验：OpenCV 解码的尺寸应与已知匹配（容忍 ±2，编码对齐波动）
        if abs(full_w - width) <= 2 and abs(full_h - height) <= 2:
            pass
        elif full_w >= width and full_h >= height:
            frame = frame[:height, :width]
        else:
            frame = None  # 尺寸差距太大，放弃走 ffmpeg

    if frame is None:
        try:
            result = subprocess.run(
                [_ffmpeg_cmd(), '-y', '-ss', str(timestamp), '-i', str(video_path),
                 '-frames:v', '1',
                 '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                capture_output=True, timeout=30, creationflags=SUBPROCESS_FLAGS
            )
            expected = width * height
            if not result.stdout or len(result.stdout) < expected:
                return None
            arr = np.frombuffer(result.stdout, dtype=np.uint8)[:expected]
            frame = arr.reshape(height, width)
        except Exception:
            _log_error(f"extract_gray_frame fallback ffmpeg: {video_path}")
            return None

    if crop_y is not None and crop_h is not None:
        y0 = max(0, min(crop_y, frame.shape[0] - 1))
        y1 = min(frame.shape[0], y0 + crop_h)
        if y1 <= y0:
            return None
        return frame[y0:y1, :].copy()
    return frame


def natural_sort_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def get_video_fps(video_path):
    """轻量获取视频帧率（仅查询 r_frame_rate，速度快）"""
    try:
        result = subprocess.run(
            [_ffprobe_cmd(), '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate',
             '-of', 'default=noprint_wrappers=1:nokey=1',
             str(video_path)],
            capture_output=True, timeout=15, creationflags=SUBPROCESS_FLAGS
        )
        if result.returncode == 0 and result.stdout:
            fps_str = decode_output(result.stdout).strip()
            num, den = fps_str.split('/')
            if float(den) != 0:
                return round(float(num) / float(den), 2)
    except Exception:
        pass
    return 0.0


# ============================================================
# v4.0 新增检测项
# ============================================================

def check_version_durations(video_paths):
    """检查同一视频各版本时长是否一致。
    video_paths: {文件夹名: 文件路径}
    返回: (all_consistent, {folder: duration, ...})
    """
    durations = {}
    for folder, path in video_paths.items():
        dur = get_video_duration(path)
        if dur > 0:
            durations[folder] = round(dur, 2)

    if len(durations) <= 1:
        return True, durations

    vals = list(durations.values())
    consistent = max(vals) - min(vals) <= DURATION_TOLERANCE
    return consistent, durations


def detect_starting_black_frames(video_path, check_seconds=START_CHECK_SECONDS):
    """检测视频开头的黑帧"""
    return detect_ending_black_frames(video_path, check_seconds,
                                       check_seconds=check_seconds)


def _dynamic_timeout(duration, base=60, per_minute=3):
    """根据视频时长动态计算 ffmpeg 超时时间"""
    if duration <= 0:
        return base
    return max(base, base + (duration / 60) * per_minute)


# ============================================================
# v5.0 高级检测 — OpenCV 真 Sobel + PSNR + SSIM
# ============================================================

def extract_subtitle_region_frame(video_path, timestamp, width, height,
                                   sub_y, sub_h, sub_x=0, sub_w=None):
    """提取视频指定时刻的字幕区域灰度帧（用于两版同帧像素级对比）。

    与 edge_density_opencv 使用完全一致的裁剪链路，确保同数据域。
    帧不做任何二值化/边缘处理 → 保证 CP 帧与 NS 帧在同一语义域可比。
    """
    if sub_w is None or sub_w <= 0:
        sub_x = 0
        sub_w = width
    frame = extract_gray_frame(video_path, timestamp, width, height,
                                crop_y=sub_y, crop_h=sub_h)
    if frame is None:
        return None
    if sub_x > 0 or sub_w < width:
        x0 = max(0, min(sub_x, frame.shape[1] - 1))
        x1 = min(frame.shape[1], x0 + sub_w)
        if x1 <= x0:
            return None
        frame = frame[:, x0:x1]
    return frame


def edge_density_opencv(video_path, timestamp, sub_y, sub_h,
                        sub_x=0, sub_w=0, width=None, height=None):
    """用 OpenCV 对指定帧的字幕区域做真 Sobel 边缘检测。
    修复版：先取完整帧信息，按完整尺寸提取帧再 numpy 裁剪。
    优化：优先使用调用方传入的 width/height，避免内部重复 ffprobe。
    """
    if width is None or height is None:
        info = get_video_info(video_path)
        if not info:
            return 0.0
        full_w = info['width']
        full_h = info['height']
    else:
        full_w = width
        full_h = height
    if sub_w <= 0:
        sub_w = full_w
    frame = extract_subtitle_region_frame(video_path, timestamp, full_w, full_h,
                                           sub_y, sub_h, sub_x, sub_w)
    if frame is None:
        return 0.0
    gx = cv2.Sobel(frame, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(frame, cv2.CV_64F, 0, 1, ksize=3)
    grad = np.sqrt(gx ** 2 + gy ** 2)
    return float(np.mean(grad > 40) * 100)


def compute_psnr(img1, img2):
    """计算两帧灰度图的 PSNR"""
    if img1 is None or img2 is None:
        return 0.0
    if img1.shape != img2.shape:
        h = min(img1.shape[0], img2.shape[0])
        w = min(img1.shape[1], img2.shape[1])
        img1, img2 = img1[:h, :w], img2[:h, :w]
    mse = np.mean((img1.astype(np.float64) - img2.astype(np.float64)) ** 2)
    if mse < 1e-10:
        return 100.0
    return round(20 * np.log10(255.0 / np.sqrt(mse)), 1)


def compute_ssim(img1, img2):
    """计算两帧灰度图的 SSIM（简化版，OpenCV 实现）"""
    if img1 is None or img2 is None:
        return 0.0
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    mu1 = cv2.GaussianBlur(img1.astype(np.float64), (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(img2.astype(np.float64), (11, 11), 1.5)
    mu1_sq = mu1 ** 2; mu2_sq = mu2 ** 2
    mu1_mu2 = mu1 * mu2
    sigma1_sq = cv2.GaussianBlur((img1.astype(np.float64)) ** 2, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur((img2.astype(np.float64)) ** 2, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur((img1.astype(np.float64) * img2.astype(np.float64)), (11, 11), 1.5) - mu1_mu2
    num = (2 * mu1_mu2 + C1) * (2 * sigma12 + C2)
    den = (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    ssim_map = num / (den + 1e-10)
    return round(float(np.mean(ssim_map)), 4)


def compute_mae(img1, img2):
    """计算两帧灰度图的平均绝对误差 MAE（对字幕这种局部亮/暗斑更敏感）"""
    if img1 is None or img2 is None:
        return 255.0
    if img1.shape != img2.shape:
        h = min(img1.shape[0], img2.shape[0])
        w = min(img1.shape[1], img2.shape[1])
        img1, img2 = img1[:h, :w], img2[:h, :w]
    return round(float(np.mean(np.abs(img1.astype(np.float64) - img2.astype(np.float64)))), 2)


def compare_versions_by_framediff(cp_path, ns_path, timestamps,
                                  width, height, sub_y, sub_h, sub_x=0, sub_w=None):
    """帧差直判：成片 vs 无字幕版同时刻，像素级对比字幕区域。

    核心思想（用户提出）：成片必须有字幕叠加 → 与 NS 同帧比应该差异明显。

    判定逻辑（v2）：逐帧检查，只要 ANY 一帧出现显著差异 → 该时刻成片有字幕而
    NS 没有 → NS 正常（无硬字幕）。只有 ALL 帧都几乎像素级一致 → NS 疑似带了
    同样的硬字幕 → 异常。

    采用密集采样 + 遇差异即停（early exit），确保能命中真正的字幕时刻（edge
    density 高不等于有字幕，场景内容也会产生边缘），同时对正常 NS 快速返回。

    返回: dict
        - 'usable': bool        是否有足够的有效帧对来判定
        - 'pairs': int          有效帧对数（含 early exit 前已检查的）
        - 'avg_ssim': float     平均 SSIM
        - 'avg_psnr': float     平均 PSNR
        - 'avg_mae': float      平均 MAE
        - 'ns_looks_same': bool NS是否所有帧都与成片一致（疑似带字幕）
        - 'diff_found': bool    是否找到差异帧（True → NS 正常）
        - 'detail_per_ts': list 每帧详情 [(ts, ssim, psnr, mae), ...]
    """
    if sub_w is None or sub_w <= 0:
        sub_x = 0
        sub_w = width

    # 单帧"有差异"判定阈值：任一指标超出即认为该帧有差异
    # 字幕叠加造成的差异通常很显著（SSIM~0.94, PSNR~20, MAE~3+），
    # 而无字幕时两版几乎完全一致（SSIM~1.0, PSNR~100, MAE~0）
    FRAME_DIFF_SSIM = 0.99   # SSIM < 此值 → 该帧有差异
    FRAME_DIFF_PSNR = 50.0   # PSNR < 此值 → 该帧有差异
    FRAME_DIFF_MAE = 1.0     # MAE > 此值 → 该帧有差异
    MIN_USABLE_PAIRS = 2

    detail_per_ts = []
    diff_found = False

    for ts in timestamps:
        cp_frame = extract_subtitle_region_frame(cp_path, ts, width, height,
                                                  sub_y, sub_h, sub_x, sub_w)
        ns_frame = extract_subtitle_region_frame(ns_path, ts, width, height,
                                                  sub_y, sub_h, sub_x, sub_w)
        if cp_frame is None or ns_frame is None:
            continue
        ssim = compute_ssim(cp_frame, ns_frame)
        psnr = compute_psnr(cp_frame, ns_frame)
        mae = compute_mae(cp_frame, ns_frame)
        detail_per_ts.append((round(ts, 2), ssim, psnr, mae))

        # 任一指标显示差异 → 该时刻成片有字幕而NS没有 → NS正常，立即返回
        if ssim < FRAME_DIFF_SSIM or psnr < FRAME_DIFF_PSNR or mae > FRAME_DIFF_MAE:
            diff_found = True
            break  # early exit：一帧差异足以证明NS无字幕

    # 找到差异帧 → 1帧即足够判定NS正常（conclusive），usable=True
    # 未找到差异 → 需至少 MIN_USABLE_PAIRS 帧全部一致才能定罪"NS有字幕"
    if diff_found:
        usable = len(detail_per_ts) >= 1
    else:
        usable = len(detail_per_ts) >= MIN_USABLE_PAIRS

    if not usable:
        return {
            'usable': False, 'pairs': len(detail_per_ts),
            'avg_ssim': 0.0, 'avg_psnr': 0.0, 'avg_mae': 0.0,
            'ns_looks_same': False, 'diff_found': diff_found,
            'detail_per_ts': detail_per_ts,
        }

    ssims = [d[1] for d in detail_per_ts]
    psnrs = [d[2] for d in detail_per_ts]
    maes = [d[3] for d in detail_per_ts]
    avg_ssim = round(sum(ssims) / len(ssims), 4)
    avg_psnr = round(sum(psnrs) / len(psnrs), 1)
    avg_mae = round(sum(maes) / len(maes), 2)

    # 找到差异帧 → NS 正常（无硬字幕）；所有帧都一致 → NS 疑似带字幕
    ns_looks_same = not diff_found

    return {
        'usable': True, 'pairs': len(detail_per_ts),
        'avg_ssim': avg_ssim, 'avg_psnr': avg_psnr, 'avg_mae': avg_mae,
        'ns_looks_same': ns_looks_same, 'diff_found': diff_found,
        'detail_per_ts': detail_per_ts,
    }


def compare_frames_quality(video_paths, timestamps, width=None, height=None):
    """多版本同帧画质对比：返回 PSNR/SSIM 矩阵
    video_paths: [(版本名, 路径), ...]
    timestamps: 采样时间点列表
    width/height: 可选，视频分辨率，传入可避免内部重复 ffprobe
    """
    results = {name: [] for name, _ in video_paths}
    for ts in timestamps:
        frames = {}
        for name, path in video_paths:
            if os.path.exists(path):
                f = _extract_full_rgb_frame(path, ts, width=width, height=height)
                if f is not None:
                    frames[name] = f
        if len(frames) >= 2:
            names = list(frames.keys())
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    psnr = compute_psnr(frames[names[i]], frames[names[j]])
                    ssim = compute_ssim(frames[names[i]], frames[names[j]])
                    results[names[i]].append({
                        'vs': names[j], 'psnr': psnr, 'ssim': ssim,
                    })
                    results[names[j]].append({
                        'vs': names[i], 'psnr': psnr, 'ssim': ssim,
                    })
    return results


def _extract_full_rgb_frame(video_path, timestamp, width=None, height=None):
    """提取完整 RGB 帧。
    优先走 OpenCV VideoCapture，失败 fallback 到 ffmpeg。
    width/height 可选，传入可加速尺寸校验。
    """
    frame = _extract_frame_opencv(video_path, timestamp, want_rgb=True)
    if frame is not None:
        full_h, full_w = frame.shape[:2]
        if width and height:
            if abs(full_w - width) <= 2 and abs(full_h - height) <= 2:
                return frame
            elif full_w >= width and full_h >= height:
                return frame[:height, :width]
            else:
                frame = None
        else:
            return frame

    # ffmpeg fallback
    try:
        result = subprocess.run(
            [_ffmpeg_cmd(), '-y', '-ss', str(timestamp), '-i', str(video_path),
             '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
            capture_output=True, timeout=30, creationflags=SUBPROCESS_FLAGS
        )
        if not result.stdout:
            return None
        if width is None or height is None:
            info = get_video_info(video_path)
            if not info:
                return None
            w, h = info['width'], info['height']
        else:
            w, h = width, height
        arr = np.frombuffer(result.stdout, dtype=np.uint8)
        if len(arr) < w * h * 3:
            return None
        return arr[:w * h * 3].reshape(h, w, 3)
    except Exception:
        return None


# ============================================================
# 基础设施工具类
# ============================================================

def atomic_write_json(path, data):
    """原子写入 JSON 文件，避免中途崩溃导致文件损坏。
    先写入 .tmp 临时文件，写完后 os.replace 原子替换。
    """
    dir_path = os.path.dirname(str(path))
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class VideoInfoCache:
    """预扫描缓存：一次 ffprobe 取出全部信息（duration/fps/resolution/codec），
    后续所有检测函数从缓存读取，避免重复 fork ffprobe 子进程。

    线程安全：检测常以 ThreadPoolExecutor 并行执行，多个工作线程会并发调用
    get()。内部用锁保护读-改-写，避免同一文件被多个线程重复 ffprobe 浪费。
    """
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, video_path):
        key = str(video_path)
        with self._lock:
            if key not in self._cache:
                info = get_video_info(key)
                self._cache[key] = info  # 可能为 None
            return self._cache[key]

    def get_duration(self, video_path):
        info = self.get(video_path)
        return info.get('duration', 0.0) if info else 0.0

    def get_fps(self, video_path):
        info = self.get(video_path)
        return info.get('fps', 0.0) if info else 0.0

    def clear(self):
        with self._lock:
            self._cache.clear()


class CancelToken:
    """可取消的检测令牌：记录正在运行的子进程，取消时逐个 terminate()。
    用法:
        token = CancelToken()
        # 检测线程中检查 token.cancelled
        # 取消时调用 token.cancel()
    """
    def __init__(self):
        self.cancelled = False
        self._processes = []
        self._lock = threading.Lock()

    def register(self, proc):
        """注册一个 subprocess.Popen 对象，返回是否继续执行"""
        with self._lock:
            if self.cancelled:
                try:
                    proc.terminate()
                except Exception:
                    pass
                return False
            self._processes.append(proc)
            return True

    def unregister(self, proc):
        with self._lock:
            if proc in self._processes:
                self._processes.remove(proc)

    def cancel(self):
        """取消检测：终止所有正在运行的子进程"""
        with self._lock:
            self.cancelled = True
            for p in self._processes:
                try:
                    p.terminate()
                except Exception:
                    pass
            self._processes.clear()


# ============================================================
# 统一检测函数 — 桌面端和 Web 端共用
# ============================================================

def check_hard_subtitle(video_path, width, height, duration,
                        sub_y, sub_h, sub_x=0, sub_w=None, cache=None,
                        mode='average', sample_timestamps=None,
                        min_positive_samples=3):
    """硬字幕检测（统一版，使用 OpenCV Sobel 边缘检测）。

    模式说明:
    - mode='average'  (默认): 8帧均匀采样取平均（兼容性，与旧逻辑一致）
    - mode='first_positive': 成片快检模式 — 从视频10%位置开始逐秒扫描，
                               找到密度 > 3% 的帧即收集，直到攒够 min_positive_samples 个
                               命中（默认3个）或扫到 75% 位置。
                               速度最快：多数视频在 3~5 帧内可攒够 3 个正样本。
    - mode='at_timestamps' : 无字幕版对比模式 — 在指定时间戳提取帧，
                               与成片同一时刻对比。sample_timestamps=[ts1, ts2, ...]
    """
    if sub_w is None or sub_w <= 0:
        sub_x = 0
        sub_w = width

    HARD_SUB_QUICK_POSITIVE = 3.0   # 快检模式：密度>此值视为"找到字幕"
    HARD_SUB_QUICK_START_RATIO = 0.10   # 成片扫描起始位置（跳过片头）
    HARD_SUB_QUICK_END_RATIO = 0.80     # 成片扫描结束位置（增加覆盖）
    HARD_SUB_QUICK_STEP_SEC = 2.0       # 快检采样步长（秒）
    HARD_SUB_QUICK_MAX_FRAMES = 45      # 快检最多采样帧数（上限保护）

    timestamps = []
    if mode == 'first_positive':
        start = duration * HARD_SUB_QUICK_START_RATIO
        end = duration * HARD_SUB_QUICK_END_RATIO
        step = max(1.0, HARD_SUB_QUICK_STEP_SEC)
        ts = start
        while ts <= end and len(timestamps) < HARD_SUB_QUICK_MAX_FRAMES:
            timestamps.append(round(ts, 2))
            ts += step

    elif mode == 'at_timestamps' and sample_timestamps:
        timestamps = list(sample_timestamps)

    else:  # 'average'
        sample_count = HARD_SUB_SAMPLE_FRAMES
        timestamps = [round(duration * (i + 0.5) / sample_count, 2)
                      for i in range(sample_count)]

    densities = []
    hits = []  # (ts, density) 用于回传
    positive_count = 0

    for ts in timestamps:
        d = edge_density_opencv(video_path, ts, sub_y, sub_h, sub_x, sub_w,
                                width=width, height=height)
        if d > 0:
            densities.append(d)
            hits.append((ts, round(d, 2)))
        if mode == 'first_positive' and d >= HARD_SUB_QUICK_POSITIVE:
            positive_count += 1
            if positive_count >= min_positive_samples:
                # 攒够命中数量 → 提前停止
                break

    if not densities:
        return {'has_hardsub': False, 'avg_density': 0, 'max_density': 0,
                'error': '帧提取失败', 'samples': hits,
                'found_positive': False, 'samples_count': 0,
                'positive_count': 0}

    avg_d = sum(densities) / len(densities)
    max_d = max(densities)
    result = {
        'has_hardsub': avg_d > EDGE_DENSITY_HIGH_ABSOLUTE,
        'avg_density': round(avg_d, 2),
        'max_density': round(max_d, 2),
        'samples': hits,
        'samples_count': len(hits),
        'positive_count': positive_count,
    }
    if mode == 'first_positive':
        result['found_positive'] = positive_count >= min_positive_samples
    return result


def _density_based_ns_hardsub(ns_d, cp_density, has_reference, max_no_sub,
                               gap_pct, fallback_ratio, diag_entry):
    """帧差法不可用时，用密度法判定 NS 是否有硬字幕。"""
    if has_reference and cp_density > 2.0:
        gap = cp_density - ns_d
        ratio = ns_d / cp_density if cp_density > 0 else 0
        diag_entry['method'] = 'density_fallback'
        diag_entry['gap'] = round(gap, 2)
        diag_entry['ratio'] = round(ratio, 3)
        if gap >= gap_pct:
            has_hs = False
            diag_entry['reason'] = f"密度法：CP-NS差值={gap:.2f}% ≥ {gap_pct}% → 字幕只在成片，NS正常"
        elif cp_density >= 5.0:
            has_hs = (gap < gap_pct) and (ratio > fallback_ratio)
            diag_entry['reason'] = (
                f"密度法(CP≥5%)：差值<{gap_pct}%且比值>{int(fallback_ratio*100)}% → "
                f"gap={gap:.2f}, ratio={ratio:.2%} → "
                f"{'NS疑似有字幕' if has_hs else '条件未满足→NS正常'}"
            )
        elif cp_density >= 3.0:
            has_hs = (gap < 0.6) and (ratio > 0.85) and (ns_d > EDGE_DENSITY_HIGH)
            diag_entry['reason'] = (
                f"密度法(CP 3~5%)：差值<0.6 + 比值>85% + NS>{EDGE_DENSITY_HIGH}% → "
                f"gap={gap:.2f}, ratio={ratio:.2%}, ns_d={ns_d:.2f} → "
                f"{'NS疑似有字幕' if has_hs else '条件未满足→NS正常'}"
            )
        else:
            has_hs = ns_d > EDGE_DENSITY_HIGH_ABSOLUTE
            diag_entry['reason'] = (
                f"密度法(CP 2~3%)：NS密度 vs 绝对阈值 {EDGE_DENSITY_HIGH_ABSOLUTE}% → "
                f"ns_d={ns_d:.2f} → {'NS疑似有字幕' if has_hs else 'NS正常'}"
            )
    else:
        diag_entry['method'] = 'density_fallback'
        has_hs = ns_d > EDGE_DENSITY_HIGH_ABSOLUTE
        diag_entry['reason'] = (
            f"密度法(无参考/CP极低)：NS密度 vs 绝对阈值 {EDGE_DENSITY_HIGH_ABSOLUTE}% → "
            f"ns_d={ns_d:.2f} → {'NS疑似有字幕' if has_hs else 'NS正常'}"
        )
    return has_hs


def process_single_video(base, vfile, info, cache=None, cancel_token=None):
    """统一检测单个视频（桌面端和 Web 端共用）。

    Args:
        base: 项目根目录
        vfile: 视频文件名（含扩展名）
        info: dict，包含 cp_folder, hardsub_folders, all_video_folders,
              width, height, sub_y, sub_h, sub_x, sub_w,
              opt_blackframes, opt_hardsubs, opt_duration
        cache: VideoInfoCache 实例（可选，避免重复 ffprobe）
        cancel_token: CancelToken 实例（可选，支持取消）

    Returns:
        dict: 检测结果
    """
    vname = os.path.splitext(vfile)[0]
    t_start = time.perf_counter()
    cp_folder = info['cp_folder']
    hardsub_folders = info['hardsub_folders']
    all_video_folders = info['all_video_folders']
    width = info['width']
    height = info['height']
    sub_y = info['sub_y']
    sub_h = info['sub_h']
    sub_x = info.get('sub_x', 0)
    sub_w = info.get('sub_w', width)

    cp_path = os.path.join(base, cp_folder, vfile)
    if cache:
        duration = cache.get_duration(cp_path)
    else:
        duration = get_video_duration(cp_path)

    result = {
        'video': vname,
        'duration': duration,
        'black_frames': {},
        'hard_sub': {},
        'duration_check': {},
        'fps_check': {},
        'issues': [],
        'status': 'pass',
        'timing': {'duration': 0, 'bf': 0, 'hs': 0, 'extra': 0},
    }

    # --- 结尾黑帧检测 ---
    if info.get('opt_blackframes'):
        t_bf = time.perf_counter()
        for folder in all_video_folders:
            if cancel_token and cancel_token.cancelled:
                break
            path = os.path.join(base, folder, vfile)
            if os.path.exists(path):
                ver_duration = (duration if folder == cp_folder
                                else (cache.get_duration(path) if cache
                                      else get_video_duration(path)))
                bf = detect_ending_black_frames(path, ver_duration)
                result['black_frames'][folder] = bf
                if bf and folder == cp_folder:
                    result['issues'].append('BLACK_FRAME')
                    if result['status'] == 'pass':
                        result['status'] = 'warn'
        result['timing']['bf'] = round(time.perf_counter() - t_bf, 2)

    # --- 硬字幕检测（快检 + 时间戳共享对比） ---
    # 成片（cp_folder）：用 first_positive 模式，找到 3 个带字幕时刻即停（通常3~5帧）
    # 无字幕版本：用成片的 3 个命中时刻做定点对比（3帧即可）
    #
    # 速度收益：
    #   成片 3~5 帧 / 旧8帧 → 节省 40~60%
    #   无字幕版 3 帧定点 / 旧8帧 → 节省 60%
    #   对比精度也更好：完全相同的画面时刻，差异只能来自字幕叠加
    if info.get('opt_hardsubs'):
        t_hs = time.perf_counter()
        cp_hs = None
        cp_hs_ts_for_compare = None  # 传给无字幕版的定点时间戳

        # 第一步：先检测成片（快检模式，攒够3个命中即停）
        if cp_folder in all_video_folders:
            if cancel_token and cancel_token.cancelled:
                pass
            else:
                hpath = os.path.join(base, cp_folder, vfile)
                if os.path.exists(hpath):
                    cp_hs = check_hard_subtitle(
                        hpath, width, height, duration,
                        sub_y, sub_h, sub_x, sub_w, cache,
                        mode='first_positive', min_positive_samples=3)
                    result['hard_sub'][cp_folder] = cp_hs
                    # 抽命中时刻的时间戳给无字幕版定点对比
                    if cp_hs.get('samples'):
                        pos_ts = [s[0] for s in cp_hs['samples'] if s[1] >= 3.0][:3]
                        if len(pos_ts) < 3 and cp_hs['samples']:
                            # 不足3个，用密度最高的补齐
                            by_density = sorted(cp_hs['samples'],
                                                key=lambda s: -s[1])
                            for s in by_density:
                                if s[0] not in pos_ts:
                                    pos_ts.append(s[0])
                                    if len(pos_ts) >= 3:
                                        break
                        cp_hs_ts_for_compare = pos_ts[:3] if pos_ts else None

        # 第二步：检测无字幕版本
        #   a) 密度法：check_hard_subtitle（定点对比/快检回退）→ 保留 avg_density 等指标
        #   b) 帧差法（优先级最高）：密集采样成片 vs NS 同时刻 像素级对比
        #      帧差法 usable=True 时，后续判定直接采用其结论（避免画面内容/台标导致误报）
        #
        # 密集采样时间戳：每2秒一帧，覆盖10%~80%时长，最多30帧
        # （edge density 高≠有字幕，场景内容也产生边缘 → 必须密集采样才能命中
        #   真正的字幕时刻；帧差法遇差异即停，正常NS只需检查几帧）
        fd_start = duration * 0.10
        fd_end = duration * 0.80
        fd_timestamps = []
        _ts = fd_start
        while _ts <= fd_end and len(fd_timestamps) < 30:
            fd_timestamps.append(round(_ts, 2))
            _ts += 2.0

        frame_diff_by_folder = {}  # {folder: compare_versions_by_framediff result}
        cp_path_for_diff = os.path.join(base, cp_folder, vfile)
        for hf in all_video_folders:
            if hf == cp_folder:
                continue
            if cancel_token and cancel_token.cancelled:
                break
            hpath = os.path.join(base, hf, vfile)
            if os.path.exists(hpath):
                hs_duration = (cache.get_duration(hpath) if cache
                               else get_video_duration(hpath))
                # NS 密度检测（用于展示和帧差法不可用时的回退）
                if cp_hs_ts_for_compare:
                    hs = check_hard_subtitle(
                        hpath, width, height, hs_duration,
                        sub_y, sub_h, sub_x, sub_w, cache,
                        mode='at_timestamps',
                        sample_timestamps=cp_hs_ts_for_compare)
                else:
                    hs = check_hard_subtitle(
                        hpath, width, height, hs_duration,
                        sub_y, sub_h, sub_x, sub_w, cache,
                        mode='first_positive', min_positive_samples=3)
                result['hard_sub'][hf] = hs

                # 帧差法（主判定方法）：密集采样 + 遇差异即停
                if os.path.exists(cp_path_for_diff) and fd_timestamps:
                    fd = compare_versions_by_framediff(
                        cp_path_for_diff, hpath, fd_timestamps,
                        width, height, sub_y, sub_h, sub_x, sub_w)
                    frame_diff_by_folder[hf] = fd
                    if fd['usable']:
                        hs['frame_diff'] = {
                            'pairs': fd['pairs'],
                            'avg_ssim': fd['avg_ssim'],
                            'avg_psnr': fd['avg_psnr'],
                            'avg_mae': fd['avg_mae'],
                            'ns_looks_same': fd['ns_looks_same'],
                        }

        # 收集各版本密度（定点对比：用 avg_density 对比，多帧平均更稳）
        cp_density = (cp_hs or {}).get('avg_density', 0)
        no_sub_densities = {}
        for f in all_video_folders:
            if f != cp_folder and f in result['hard_sub']:
                no_sub_densities[f] = result['hard_sub'][f].get('avg_density', 0)
        max_no_sub = max(no_sub_densities.values()) if no_sub_densities else 0
        has_reference = bool(no_sub_densities)

        # ================================================================
        # 硬字幕最终判定 — 以帧差法为绝对权威（先定CP真相，再定各NS）
        #
        # 帧差法是最客观的：NS干净、时间戳对齐、同分辨率同编码 → 差异
        # 唯一来源就是CP上叠加的字幕。密度法永远是辅助/回退。
        #
        # 真相判定（CP 是否真的有字幕叠加）：
        #   ANY(NS的帧差法 diff_found=True) → CP有字幕叠加（100%可信）
        #   ALL(NS的帧差法 ns_looks_same=True) → CP没有字幕叠加
        #       （如果CP真有字幕，所有NS都一模一样才叫NS也带字幕；
        #        但CP没字幕时所有NS看起来也都一样，这种场景不能定罪NS）
        #   帧差法不可用 → 回退到密度法
        # ================================================================
        fd_results = {hf: frame_diff_by_folder.get(hf) for hf in all_video_folders
                      if hf != cp_folder and hf in frame_diff_by_folder}

        usable_fds = {hf: f for hf, f in fd_results.items() if f and f['usable']}
        any_diff_found = any(f.get('diff_found') for f in usable_fds.values())
        all_looks_same = (len(usable_fds) >= 1 and
                          all(f.get('ns_looks_same') for f in usable_fds.values()))

        MIN_HARDSUB_GAP_PCT = 0.8
        MIN_HARDSUB_GAP_FOR_CONFIRM = 0.5
        FALLBACK_RATIO_THRESHOLD = 0.82

        for hf in all_video_folders:
            if hf not in result['hard_sub']:
                continue
            hs = result['hard_sub'][hf]
            avg_d = hs.get('avg_density', 0)

            if hf == cp_folder:
                # ---------- 成片硬字幕判定 ----------
                cp_has_hs_quick = (cp_hs or {}).get('found_positive', False)
                cp_hs_via_frame_diff = False  # 最终：帧差法给出的CP真相

                if usable_fds:
                    if any_diff_found:
                        # 至少一个NS发现了像素差异 → CP确实有字幕叠加
                        cp_hs_via_frame_diff = True
                    elif all_looks_same:
                        # 所有NS都和CP像素一致 → CP根本没有字幕
                        cp_hs_via_frame_diff = False
                    else:
                        # 混合情况（部分可用但结论不一致）→ 以密度法兜底
                        cp_hs_via_frame_diff = None
                else:
                    # 帧差法全都不可用 → 交给密度法
                    cp_hs_via_frame_diff = None

                if cp_hs_via_frame_diff is not None:
                    has_hs = cp_hs_via_frame_diff
                elif has_reference and max_no_sub > 1.0:
                    has_hs = cp_has_hs_quick or (
                        cp_density > 2.0 and (
                            (cp_density - max_no_sub) >= MIN_HARDSUB_GAP_FOR_CONFIRM
                            or cp_density >= max_no_sub * 1.20))
                else:
                    has_hs = cp_has_hs_quick or (avg_d > EDGE_DENSITY_HIGH)
                if not has_hs:
                    result['issues'].append(f'NO_HARDSUB:{hf}')
                    result['status'] = 'fail'
            else:
                # ---------- 无字幕版本硬字幕判定 ----------
                ns_d = avg_d
                diag_entry = {
                    'folder': hf,
                    'ns_density': round(ns_d, 2),
                    'cp_density': round(cp_density, 2),
                    'gap': round(cp_density - ns_d, 2) if (cp_density or ns_d) else 0,
                    'ratio': round(ns_d / cp_density, 3) if cp_density > 0 else 0,
                }
                fd = fd_results.get(hf)
                ns_has_hs = False  # 最终结论

                if fd and fd['usable']:
                    diag_entry['method'] = 'frame_diff'
                    diag_entry['frame_diff_usable'] = True
                    diag_entry['pairs'] = fd['pairs']
                    diag_entry['avg_ssim'] = fd['avg_ssim']
                    diag_entry['avg_psnr'] = fd['avg_psnr']
                    diag_entry['avg_mae'] = fd['avg_mae']
                    diag_entry['diff_found'] = fd.get('diff_found', False)
                    diag_entry['thresholds'] = {
                        'ssim_diff': 0.99, 'psnr_diff': 50.0, 'mae_diff': 1.0,
                        'note': '先定CP真相：any_diff_found→CP有字幕；all_looks_same→CP没字幕→NS不背锅'
                    }
                    diag_entry['ns_looks_same'] = fd['ns_looks_same']
                    diag_entry['any_diff_found_globally'] = any_diff_found
                    diag_entry['all_looks_same_globally'] = all_looks_same

                    if fd.get('diff_found'):
                        # 自己就发现了差异帧 → NS正常（字幕只在CP）
                        ns_has_hs = False
                        diag_entry['reason'] = (
                            f"帧差法：第{fd['pairs']}帧发现显著差异"
                            f" → 成片有字幕而NS无→NS正常"
                        )
                    elif all_looks_same:
                        # 自己没发现差异，且所有可用NS的帧差都显示CP和自己一致
                        # → CP本身就没有字幕叠加（全局判定），NS正常（不背锅）
                        ns_has_hs = False
                        diag_entry['reason'] = (
                            f"帧差法：该NS与CP像素一致，且全局所有可用NS"
                            f"都与CP一致 → CP本身就没字幕，NS正常"
                            f"（成片该报NO_HARDSUB）"
                        )
                        diag_entry['cp_may_lack_sub'] = True
                    elif any_diff_found:
                        # 自己和CP一致（没差异帧），但别的NS发现了差异帧
                        # → 说明CP确实有字幕，只是这个NS也带了同样的字幕
                        ns_has_hs = True
                        diag_entry['reason'] = (
                            f"帧差法：其他NS已证明CP有字幕(存在差异帧)，"
                            f"但该NS与CP像素一致(共{fd['pairs']}帧) → "
                            f"NS疑似带同样硬字幕"
                        )
                    else:
                        # 帧差法结果不足以判定（混合情况rare），回退密度法
                        diag_entry['reason'] = "帧差法全局判定不确定 → 回退密度法"
                        has_hs = _density_based_ns_hardsub(
                            ns_d, cp_density, has_reference, max_no_sub,
                            MIN_HARDSUB_GAP_PCT, FALLBACK_RATIO_THRESHOLD, diag_entry)
                        ns_has_hs = has_hs
                    diag_entry['detail_per_ts'] = fd.get('detail_per_ts', [])
                else:
                    # 帧差法不可用 → 纯密度法回退
                    diag_entry['frame_diff_usable'] = False
                    ns_has_hs = _density_based_ns_hardsub(
                        ns_d, cp_density, has_reference, max_no_sub,
                        MIN_HARDSUB_GAP_PCT, FALLBACK_RATIO_THRESHOLD, diag_entry)

                has_hs = ns_has_hs
                diag_entry['final_has_hardsub'] = has_hs
                if '_hardsub_diag' not in result:
                    result['_hardsub_diag'] = []
                result['_hardsub_diag'].append(diag_entry)

                if has_hs:
                    result['issues'].append(f'HARD_SUB:{hf}')
                    result['status'] = 'fail'

            # 将最终判定同步回 hard_sub 条目，保证详情显示与 issues 一致
            hs['has_hardsub'] = has_hs

        result['timing']['hs'] = round(time.perf_counter() - t_hs, 2)

    # --- v4.0 新检测项 ---
    t_extra = time.perf_counter()

    # 时长一致性
    if info.get('opt_duration'):
        ver_paths = {}
        for folder in all_video_folders:
            path = os.path.join(base, folder, vfile)
            if os.path.exists(path):
                ver_paths[folder] = path
        if len(ver_paths) > 1:
            ok, durs = check_version_durations(ver_paths)
            result['duration_check'] = durs
            if not ok:
                result['issues'].append('DURATION_MISMATCH')
                if result['status'] == 'pass':
                    result['status'] = 'warn'

    # 帧率检测（所有版本）
    fps_versions = {}
    for folder in all_video_folders:
        if cancel_token and cancel_token.cancelled:
            break
        path = os.path.join(base, folder, vfile)
        if os.path.exists(path):
            fps = cache.get_fps(path) if cache else get_video_fps(path)
            if fps > 0:
                fps_versions[folder] = fps
    if fps_versions:
        result['fps_check'] = fps_versions

    result['timing']['extra'] = round(time.perf_counter() - t_extra, 2)
    result['timing']['duration'] = (result['timing']['bf'] +
                                     result['timing']['hs'] +
                                     result['timing']['extra'])
    result['timing']['total'] = round(time.perf_counter() - t_start, 2)

    # 生成详情摘要
    details = []
    if result['black_frames']:
        cp_bf = result['black_frames'].get(cp_folder, [])
        if cp_bf:
            bps = "; ".join(f"{b['start']:.1f}-{b['end']:.1f}s" for b in cp_bf)
            details.append(f"结尾黑帧{len(cp_bf)}段: {bps}")
    for hf, hs in result['hard_sub'].items():
        has_hs = hs.get('has_hardsub', False)
        if hf == cp_folder:
            # 成片：应有硬字幕
            if has_hs:
                details.append(f"{hf}:有字幕✓")
            else:
                details.append(f"{hf}:缺字幕✗")
        else:
            # 无字幕版本：不应有硬字幕
            if has_hs:
                details.append(f"{hf}:有字幕✗")
            else:
                details.append(f"{hf}:无字幕✓")
    if result.get('duration_check'):
        durs = result['duration_check']
        vals = list(durs.values())
        if len(vals) > 1 and max(vals) - min(vals) > DURATION_TOLERANCE:
            details.append(f"时长不一致(差{max(vals)-min(vals):.1f}s)")
    if result.get('fps_check'):
        fps_vals = [f"{v:.2f}" for v in result['fps_check'].values()]
        details.append(f"FPS: {', '.join(fps_vals)}")
    result['details'] = " | ".join(details) if details else "全部通过"

    return result


def run_detection_batch(base, opts, cache=None, cancel_token=None,
                        on_progress=None, on_result=None, on_log=None,
                        only_videos=None):
    """批量检测入口（桌面端和 Web 端共用）。

    Args:
        base: 项目根目录
        opts: dict，包含 cp_folder, hardsub_folders, srt_folder,
              opt_*, workers
        cache: VideoInfoCache 实例
        cancel_token: CancelToken 实例
        on_progress(completed, total, pct): 进度回调
        on_result(result): 单个视频完成回调
        on_log(text): 日志回调
        only_videos: 可选，只检测这些文件名（断点续检传未检视频清单）。
                     不传则扫描 cp_dir 下全部视频。

    Returns:
        list: 全部检测结果
    """
    cp_folder = opts["cp_folder"]
    cp_dir = os.path.join(base, cp_folder)
    video_files = sorted(
        [f for f in os.listdir(cp_dir) if f.endswith(VIDEO_EXTS)],
        key=natural_sort_key
    )
    # 断点续检：只检测传入的未检视频，避免与已检结果重复
    if only_videos:
        video_files = [f for f in video_files if f in set(only_videos)]
    total = len(video_files)

    if not video_files:
        if on_log:
            on_log("错误: 成片文件夹中没有视频文件")
        return []

    if on_log:
        on_log(f"共 {total} 个视频待检")

    # 获取第一个视频信息
    first_video = os.path.join(cp_dir, video_files[0])
    info = cache.get(first_video) if cache else get_video_info(first_video)
    if not info:
        if on_log:
            on_log("错误: 无法读取视频信息，请检查 ffmpeg 是否可用")
        return []

    width, height = info['width'], info['height']
    fps = info.get('fps', 24.0)

    # 字幕区域：优先用用户框选的 sub_region [x, y, w, h]，否则按默认比例
    sub_region = opts.get("sub_region")
    if (isinstance(sub_region, (list, tuple)) and len(sub_region) == 4
            and all(isinstance(v, (int, float)) and v >= 0 for v in sub_region)
            and sub_region[2] > 0 and sub_region[3] > 0):
        sub_x = int(sub_region[0])
        sub_y = int(sub_region[1])
        sub_w = int(sub_region[2])
        sub_h = int(sub_region[3])
        # 边界保护
        sub_x = max(0, min(sub_x, width - 1))
        sub_w = min(sub_w, width - sub_x)
        sub_y = max(0, min(sub_y, height - 1))
        sub_h = min(sub_h, height - sub_y)
        region_src = "用户框选"
    else:
        sub_x = 0
        sub_y = int(height * SUB_Y_RATIO_START)
        sub_w = width
        sub_h = int(height * (SUB_Y_RATIO_END - SUB_Y_RATIO_START))
        region_src = "自动比例"

    if on_log:
        on_log(f"分辨率: {width}x{height}, {fps}fps")
        on_log(f"字幕区域({region_src}): X={sub_x}~{sub_x+sub_w}, Y={sub_y}~{sub_y+sub_h}")

    all_video_folders = [cp_folder] + \
        [f for f in opts.get("hardsub_folders", []) if f != cp_folder]

    folder_info = {
        'cp_folder': cp_folder,
        'hardsub_folders': opts.get("hardsub_folders", []),
        'all_video_folders': all_video_folders,
        'width': width, 'height': height,
        'fps': fps,
        'codec': info.get('codec', 'unknown'),
        'sub_y': sub_y, 'sub_h': sub_h,
        'sub_x': sub_x, 'sub_w': sub_w,
        'sub_region_source': region_src,
        'opt_blackframes': opts.get("opt_blackframes", True),
        'opt_hardsubs': opts.get("opt_hardsubs", True),
        'opt_duration': opts.get("opt_duration", True),
    }

    workers = opts.get("workers", 4)
    if on_log:
        on_log(f"开始并行检测（{workers}线程）...")

    results = []
    completed = 0
    t_batch_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for vfile in video_files:
            future = executor.submit(
                process_single_video, base, vfile, folder_info, cache, cancel_token
            )
            futures[future] = vfile

        for future in as_completed(futures):
            if cancel_token and cancel_token.cancelled:
                if on_log:
                    on_log("已取消，等待线程结束...")
                break
            try:
                result = future.result()
                results.append(result)
                completed += 1
                pct = completed / total * 100 if total > 0 else 100
                t_elapsed = time.perf_counter() - t_batch_start
                avg_per_video = t_elapsed / completed
                remaining = max(0, (total - completed) * avg_per_video)
                if on_progress:
                    on_progress(completed, total, pct)
                if on_result:
                    on_result(result)
                if on_log:
                    status_icon = {'pass': '✓', 'warn': '⚠', 'fail': '✗'}[result['status']]
                    tmg = result.get('timing', {})
                    on_log(
                        f"[{completed}/{total}] {result['video']}: {status_icon} "
                        f"{result.get('details', '')}  [{tmg.get('total', '?')}s]  "
                        f"总用时 {t_elapsed:.1f}s  平均 {avg_per_video:.1f}s/个  "
                        f"预计剩余 {remaining:.0f}s"
                    )
            except Exception as e:
                if on_log:
                    on_log(f"处理错误: {e}")
                completed += 1

    t_batch_total = time.perf_counter() - t_batch_start
    if on_log:
        on_log(
            f"===== 检测完成 总耗时 {t_batch_total:.1f}s  "
            f"({completed}个视频, 平均 {t_batch_total/max(completed,1):.1f}s/个) ====="
        )

    if cancel_token and cancel_token.cancelled:
        for f in futures:
            f.cancel()

    results.sort(key=lambda r: natural_sort_key(r['video']))

    # 帧率一致性汇总
    fps_data = {}
    for r in results:
        for folder, fps_val in r.get('fps_check', {}).items():
            if folder not in fps_data:
                fps_data[folder] = {}
            fps_data[folder][r['video']] = fps_val

    if fps_data:
        fps_values = set()
        for fmap in fps_data.values():
            fps_values.update(fmap.values())
        normal_fps = max(fps_values, key=lambda x: sum(
            1 for m in fps_data.values() for v in m.values() if v == x))
        fps_anomalies = []
        for r in results:
            for folder, fps_val in r.get('fps_check', {}).items():
                if fps_val > 0 and round(fps_val, 2) != round(normal_fps, 2):
                    r['issues'].append(f'FPS:{folder}={fps_val}(期望{normal_fps})')
                    if r['status'] == 'pass':
                        r['status'] = 'warn'
                    fps_anomalies.append((r['video'], folder, fps_val))
        if fps_anomalies and on_log:
            on_log(f"⚠ 帧率异常: {len(fps_anomalies)}个视频帧率≠{normal_fps}fps")
        elif fps_values and on_log:
            unique = sorted(set(round(v, 2) for v in fps_values))
            on_log(f"✓ 帧率一致: {', '.join(str(u)+'fps' for u in unique)}")

    # ===== 硬字幕决策诊断 JSON 输出 =====
    # 抽取每个视频每个 NS 版本的完整决策链（方法、指标、阈值、理由）
    # 写入 %USERPROFILE%\视频质检工具\hardsub_diagnostics_*.json，
    # 用户把文件发回即可精准定位"为什么被误报"。
    diag_file = None
    try:
        diag_list = []
        for r in results:
            video_name = r.get('video', '')
            diag_entries = r.pop('_hardsub_diag', None)
            if not diag_entries:
                continue
            video_entry = {
                'video': video_name,
                'status': r.get('status', ''),
                'issues': [i for i in r.get('issues', []) if i.startswith('HARD_SUB:') or i.startswith('NO_HARDSUB:')],
                'cp_hardsub': None,
                'ns_versions': diag_entries,
            }
            cp_hs = r.get('hard_sub', {}).get(folder_info.get('cp_folder', ''), {})
            if cp_hs:
                video_entry['cp_hardsub'] = {
                    'avg_density': cp_hs.get('avg_density', 0),
                    'max_density': cp_hs.get('max_density', 0),
                    'found_positive': cp_hs.get('found_positive', False),
                    'positive_count': cp_hs.get('positive_count', 0),
                    'samples': cp_hs.get('samples', []),
                }
            diag_list.append(video_entry)
        if diag_list:
            try:
                log_dir = Path.home() / "视频质检工具"
                log_dir.mkdir(parents=True, exist_ok=True)
                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                diag_file = log_dir / f"hardsub_diagnostics_{ts_str}.json"
                # 轮转：仅保留最近 3 份诊断文件
                existing = sorted(log_dir.glob("hardsub_diagnostics_*.json"), key=lambda p: p.stat().st_mtime)
                while len(existing) >= 3:
                    try:
                        existing[0].unlink()
                        existing.pop(0)
                    except Exception:
                        break
                payload = {
                    'generated_at': datetime.now().isoformat(timespec='seconds'),
                    'project_root': str(base),
                    'folders': {
                        'cp_folder': folder_info.get('cp_folder', ''),
                        'all_video_folders': folder_info.get('all_video_folders', []),
                    },
                    'sub_region': {
                        'source': folder_info.get('sub_region_source', ''),
                        'x': folder_info.get('sub_x', 0),
                        'y': folder_info.get('sub_y', 0),
                        'w': folder_info.get('sub_w', 0),
                        'h': folder_info.get('sub_h', 0),
                        'video_size': f"{folder_info.get('width', 0)}x{folder_info.get('height', 0)}",
                    },
                    'current_thresholds': {
                        'EDGE_DENSITY_HIGH': EDGE_DENSITY_HIGH,
                        'EDGE_DENSITY_HIGH_ABSOLUTE': EDGE_DENSITY_HIGH_ABSOLUTE,
                        'frame_diff': {
                            'ssim_diff': 0.99, 'psnr_diff': 50.0, 'mae_diff': 1.0,
                            'note': '逐帧检查：任一帧任一指标超出阈值→NS正常(无字幕)；全部帧一致→NS疑似有字幕'
                        }
                    },
                    'videos': diag_list,
                }
                atomic_write_json(str(diag_file), payload)
                if on_log:
                    on_log(f"[诊断] 硬字幕决策链已写入: {diag_file}")
            except Exception:
                _log_error("write_hardsub_diagnostics")
    except Exception:
        _log_error("collect_hardsub_diagnostics")

    folder_info['batch_total_seconds'] = round(t_batch_total, 2)
    folder_info['batch_videos_completed'] = completed
    return results, folder_info
