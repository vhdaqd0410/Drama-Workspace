# -*- coding: utf-8 -*-
"""统一 QA 引擎 — 包装 detection.py，提供后台线程 + 数据库 + 进度回调。

用法:
    from backend.qa_engine import qa_engine

    qa_engine.run(project_path="D:/项目X", project_name="项目X", workers=4)
    status = qa_engine.status("项目X")
    qa_engine.cancel("项目X")
"""

import os
import sys
import time
import json
import queue
import logging
import threading
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import detection
from db import db

logger = logging.getLogger("qa_engine")

VIDEO_EXTS = ('.mp4', '.mov', '.mkv', '.avi', '.flv', '.wmv')

VERSION_KEYWORDS = {
    '成片': ['成片', '完成版', 'final', 'output', 'outputs', 'export',
             'master', 'chinese', 'cn', 'with_sub', 'wsub', '完整版'],
    '无字幕版': ['无字幕', '无中字', 'nosub', 'no_sub', 'ns', 'clean',
               'without_sub', 'raw', '原版'],
    '字幕文件': ['字幕', 'srt', 'ass', 'ssa', 'subtitle', 'subtitles'],
    '其他版本': [],
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class QAEngine:
    """视频质检引擎 — 后台线程执行，支持取消/查询/进度回调。"""

    def __init__(self):
        self._threads = {}
        self._cancel_tokens = {}
        self._progress_queues = {}
        self._status_lock = threading.Lock()

    # ================================================================
    # 主入口
    # ================================================================

    def run(self, project_path, project_name, workers=4,
            progress_callback=None):
        """启动质检（后台线程，不阻塞调用方）。

        Args:
            project_path: 项目根目录（包含成片/无字幕版等子文件夹）
            project_name: 项目名（用于 DB 记录和查询）
            workers: 并行线程数
            progress_callback: 可选回调函数，签名 callback(info_dict)

        Returns:
            bool — 是否成功启动
        """
        project_path = os.path.abspath(project_path)
        if not os.path.isdir(project_path):
            logger.error("项目目录不存在: %s", project_path)
            return False

        with self._status_lock:
            if project_name in self._threads and self._threads[project_name].is_alive():
                logger.warning("项目 %s 已有质检任务在运行", project_name)
                return False

        folder_layout = self._detect_folder_layout(project_path)
        cp_folder = folder_layout.get('cp_folder')
        if not cp_folder:
            logger.error("未能识别成片文件夹，请检查目录结构: %s", project_path)
            return False

        thread = threading.Thread(
            target=self._run_worker,
            args=(project_path, project_name, folder_layout,
                  workers, progress_callback),
            name=f"QA-{project_name}",
            daemon=True,
        )

        cancel_token = detection.CancelToken()
        progress_q = queue.Queue(maxsize=100)

        with self._status_lock:
            self._threads[project_name] = thread
            self._cancel_tokens[project_name] = cancel_token
            self._progress_queues[project_name] = progress_q

        thread.start()
        logger.info("已启动质检: project=%s path=%s workers=%d",
                    project_name, project_path, workers)
        return True

    # ================================================================
    # 取消 / 状态查询
    # ================================================================

    def cancel(self, project_name):
        """取消正在运行的质检任务。"""
        with self._status_lock:
            token = self._cancel_tokens.get(project_name)
            thread = self._threads.get(project_name)

        if token is None:
            logger.warning("项目 %s 没有对应的 CancelToken", project_name)
            return False

        if thread and thread.is_alive():
            token.cancel()
            logger.info("已发送取消请求: %s", project_name)
            return True
        else:
            logger.info("项目 %s 没有正在运行的质检任务", project_name)
            return False

    def status(self, project_name):
        """查询项目当前质检状态（从 DB 最近一条 qa_run 读取）。"""
        runs = db.list_qa_runs_for_project(project_name, limit=1)
        if runs:
            return runs[0]
        return None

    def poll_progress(self, project_name, timeout=0.1):
        """从进度队列中取最新一条消息（非阻塞队列，供 Web 端轮询）。

        Returns:
            dict or None
        """
        q = self._progress_queues.get(project_name)
        if q is None:
            return None
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_running(self, project_name):
        with self._status_lock:
            t = self._threads.get(project_name)
        return bool(t and t.is_alive())

    # ================================================================
    # 文件夹自动检测
    # ================================================================

    @staticmethod
    def _detect_folder_layout(project_path):
        """扫描项目目录，自动识别各版本文件夹。

        Returns:
            dict: {
                'cp_folder': '成片',
                'hardsub_folders': ['成片'],
                'all_folders': ['成片', '无字幕版', ...],
                'other_folders': [...],
            }
        """
        layout = {
            'cp_folder': None,
            'hardsub_folders': [],
            'all_folders': [],
            'other_folders': [],
            'srt_folders': [],
        }

        try:
            entries = os.listdir(project_path)
        except OSError as e:
            logger.error("无法读取项目目录 %s: %s", project_path, e)
            return layout

        root_has_videos = any(
            f.lower().endswith(VIDEO_EXTS)
            for f in entries
            if os.path.isfile(os.path.join(project_path, f))
        )

        subdirs = [
            e for e in entries
            if os.path.isdir(os.path.join(project_path, e))
               and not e.startswith('.')
        ]

        if root_has_videos:
            layout['cp_folder'] = '.'
            layout['hardsub_folders'] = ['.']
            layout['all_folders'] = ['.']

        for subdir in subdirs:
            subdir_lower = subdir.lower()
            videos_here = any(
                f.lower().endswith(VIDEO_EXTS)
                for f in os.listdir(os.path.join(project_path, subdir))
                if os.path.isfile(os.path.join(project_path, subdir, f))
            )
            has_srt = any(
                f.lower().endswith(('.srt', '.ass', '.ssa', '.vtt'))
                for f in os.listdir(os.path.join(project_path, subdir))
                if os.path.isfile(os.path.join(project_path, subdir, f))
            )

            matched = None
            for tag, keywords in VERSION_KEYWORDS.items():
                for kw in keywords:
                    if kw.lower() in subdir_lower:
                        matched = tag
                        break
                if matched:
                    break

            if matched == '成片' and videos_here:
                layout['cp_folder'] = subdir
                if subdir not in layout['hardsub_folders']:
                    layout['hardsub_folders'].append(subdir)
                if subdir not in layout['all_folders']:
                    layout['all_folders'].append(subdir)
            elif matched == '无字幕版' and videos_here:
                layout['hardsub_folders'].append(subdir)
                if subdir not in layout['all_folders']:
                    layout['all_folders'].append(subdir)
            elif matched == '字幕文件' or has_srt:
                layout['srt_folders'].append(subdir)
            elif videos_here:
                layout['other_folders'].append(subdir)
                if subdir not in layout['all_folders']:
                    layout['all_folders'].append(subdir)

        if not layout['cp_folder'] and not root_has_videos:
            for subdir in subdirs:
                full = os.path.join(project_path, subdir)
                has_v = any(
                    f.lower().endswith(VIDEO_EXTS)
                    for f in os.listdir(full)
                    if os.path.isfile(os.path.join(full, f))
                )
                if has_v:
                    layout['cp_folder'] = subdir
                    layout['hardsub_folders'] = [subdir]
                    layout['all_folders'] = [subdir]
                    break

        if layout['cp_folder'] and layout['cp_folder'] not in layout['all_folders']:
            layout['all_folders'].insert(0, layout['cp_folder'])

        logger.info("文件夹识别结果: %s", json.dumps(layout, ensure_ascii=False))
        return layout

    # ================================================================
    # 后台工作线程
    # ================================================================

    def _run_worker(self, project_path, project_name, folder_layout,
                   workers, progress_callback):
        run_id = None
        cancel_token = self._cancel_tokens.get(project_name)
        progress_q = self._progress_queues.get(project_name)
        t_start = time.perf_counter()

        try:
            cp_folder = folder_layout['cp_folder']
            hardsub_folders = folder_layout.get('hardsub_folders', [cp_folder])

            opts = {
                'cp_folder': cp_folder,
                'hardsub_folders': hardsub_folders,
                'srt_folder': (folder_layout.get('srt_folders') or [None])[0],
                'opt_blackframes': True,
                'opt_hardsubs': True,
                'opt_duration': True,
                'workers': workers,
            }

            run_id = db.create_qa_run(project_name, started_at=_now(),
                                      status='running')
            logger.info("qa_run 创建成功: id=%d project=%s", run_id, project_name)

            progress_data = {
                'project_name': project_name,
                'status': 'running',
                'progress': 0,
                'current_video': '',
                'total': 0,
                'done': 0,
                'results': [],
            }
            self._emit(progress_q, progress_callback, progress_data)

            cache = detection.VideoInfoCache()
            partial_results = []

            def _on_progress(completed, total, pct):
                progress_data['progress'] = round(pct, 1)
                progress_data['done'] = completed
                progress_data['total'] = total
                progress_data['current_video'] = progress_data.get('_last_video', '')
                self._emit(progress_q, progress_callback, progress_data)

            def _on_result(result):
                partial_results.append(result)
                progress_data['results'] = self._to_public_results(
                    partial_results, folder_layout)
                progress_data['_last_video'] = result.get('video', '')
                progress_data['current_video'] = result.get('video', '')
                self._persist_result(run_id, result, folder_layout)

            def _on_log(text):
                logger.info("[%s] %s", project_name, text)

            results = detection.run_detection_batch(
                base=project_path,
                opts=opts,
                cache=cache,
                cancel_token=cancel_token,
                on_progress=_on_progress,
                on_result=_on_result,
                on_log=_on_log,
            )

            total = len(results)
            passed = sum(1 for r in results if r.get('status') == 'pass')
            warnings = sum(1 for r in results if r.get('status') == 'warn')
            failed = sum(1 for r in results if r.get('status') == 'fail')
            elapsed = round(time.perf_counter() - t_start, 2)

            summary = {
                'total': total,
                'passed': passed,
                'warnings': warnings,
                'failed': failed,
                'elapsed_seconds': elapsed,
                'folders': folder_layout,
                'videos': [
                    {
                        'video': r.get('video'),
                        'status': r.get('status'),
                        'issues': r.get('issues', []),
                        'details': r.get('details', ''),
                    }
                    for r in results
                ],
            }

            run_status = 'cancelled' if (cancel_token and cancel_token.cancelled) else 'done'

            db.update_qa_run(
                run_id,
                status=run_status,
                finished_at=_now(),
                total=total,
                passed=passed,
                warnings=warnings,
                failed=failed,
                elapsed_seconds=elapsed,
                summary_json=summary,
            )

            progress_data['status'] = run_status
            progress_data['progress'] = 100
            progress_data['total'] = total
            progress_data['done'] = total
            progress_data['results'] = self._to_public_results(results, folder_layout)
            progress_data.pop('_last_video', None)
            self._emit(progress_q, progress_callback, progress_data)

            logger.info(
                "质检完成: project=%s status=%s total=%d pass=%d warn=%d fail=%d elapsed=%.1fs",
                project_name, run_status, total, passed, warnings, failed, elapsed
            )

        except Exception as e:
            tb = traceback.format_exc()
            logger.error("质检异常: project=%s err=%s\n%s", project_name, e, tb)
            elapsed = round(time.perf_counter() - t_start, 2)
            if run_id is not None:
                try:
                    db.update_qa_run(
                        run_id,
                        status='error',
                        finished_at=_now(),
                        elapsed_seconds=elapsed,
                        summary_json={'error': str(e), 'traceback': tb[-2000:]},
                    )
                except Exception as db_err:
                    logger.error("更新 qa_run 失败: %s", db_err)

            err_data = {
                'project_name': project_name,
                'status': 'error',
                'progress': 0,
                'current_video': '',
                'total': 0,
                'done': 0,
                'results': [],
                'error': str(e),
            }
            self._emit(progress_q, progress_callback, err_data)

        finally:
            with self._status_lock:
                self._threads.pop(project_name, None)
                self._cancel_tokens.pop(project_name, None)
                if progress_q is not None:
                    try:
                        while not progress_q.empty():
                            progress_q.get_nowait()
                    except queue.Empty:
                        pass
                    self._progress_queues.pop(project_name, None)

    # ================================================================
    # 工具函数
    # ================================================================

    @staticmethod
    def _emit(progress_q, callback, data):
        if progress_q is not None:
            try:
                progress_q.put_nowait(dict(data))
            except queue.Full:
                try:
                    progress_q.get_nowait()
                    progress_q.put_nowait(dict(data))
                except Exception:
                    pass
        if callback is not None:
            try:
                callback(dict(data))
            except Exception as e:
                logger.debug("progress_callback 抛异常: %s", e)

    @staticmethod
    def _to_public_results(results, folder_layout):
        cp_folder = folder_layout.get('cp_folder', '')
        out = []
        for r in results:
            video = r.get('video', '')
            cp_info = r.get('hard_sub', {}).get(cp_folder, {}) if cp_folder else {}
            fps_val = cp_info.get('fps') or 0
            resolution = cp_info.get('resolution', '')
            if not resolution:
                w = cp_info.get('width')
                h = cp_info.get('height')
                if w and h:
                    resolution = f"{w}x{h}"

            start_black = r.get('black_frames', {}).get(cp_folder, [])
            start_black_ms = 0
            end_black_ms = 0
            if start_black:
                first = start_black[0]
                last = start_black[-1]
                start_black_ms = int(first.get('start', 0) * 1000)
                end_black_ms = int(last.get('end', 0) * 1000)

            issues = r.get('issues', [])
            details = r.get('details', '') or (', '.join(issues) if issues else '')

            subtitle_ok = not any(
                i.startswith('HARD_SUB:') or i.startswith('NO_HARDSUB:')
                for i in issues
            )
            audio_ok = not any('AUDIO' in i for i in issues)

            status_map = {'pass': 'pass', 'warn': 'warning', 'fail': 'fail'}
            public_status = status_map.get(r.get('status', 'pass'), 'pass')

            out.append({
                'video': video,
                'version': cp_folder,
                'status': public_status,
                'details': details,
                'duration': round(r.get('duration', 0), 2),
                'fps': fps_val,
                'resolution': resolution,
                'start_black_ms': start_black_ms,
                'end_black_ms': end_black_ms,
                'subtitle_ok': subtitle_ok,
                'audio_ok': audio_ok,
            })
        return out

    @staticmethod
    def _persist_result(run_id, result, folder_layout):
        try:
            cp_folder = folder_layout.get('cp_folder', '')
            status_map = {'pass': 'pass', 'warn': 'warning', 'fail': 'fail'}
            status = status_map.get(result.get('status', 'pass'), 'pass')
            issues = result.get('issues', [])
            details = result.get('details', '') or (', '.join(issues) if issues else '')

            frame_count = 0
            fps = 0.0
            resolution = ''
            cp_hs = result.get('hard_sub', {}).get(cp_folder, {}) if cp_folder else {}
            if cp_hs:
                fps = cp_hs.get('fps', 0) or 0.0
                w = cp_hs.get('width')
                h = cp_hs.get('height')
                if w and h:
                    resolution = f"{w}x{h}"
            if not resolution:
                fps_check = result.get('fps_check', {})
                for v, fv in fps_check.items():
                    if fv:
                        fps = fv
                        break

            db.insert_qa_result(
                qa_run_id=run_id,
                video_name=result.get('video', ''),
                version=cp_folder,
                status=status,
                details=details,
                frame_count=frame_count,
                fps=fps,
                resolution=resolution,
            )
        except Exception as e:
            logger.error("写入 qa_result 失败: %s", e)


qa_engine = QAEngine()
