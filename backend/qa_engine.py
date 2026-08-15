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
import re
import time
import json
import queue
import tempfile
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
SRT_EXTS = ('.srt', '.ass', '.ssa', '.vtt')

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
        self._latest_progress = {}   # {project_name: latest_progress_dict}
        self._progress_lock = threading.Lock()
        self._status_lock = threading.Lock()

    # ================================================================
    # 主入口
    # ================================================================

    def run(self, project_path, project_name, workers=4,
            progress_callback=None, opts=None, folder_layout=None):
        """启动质检（后台线程，不阻塞调用方）。

        Args:
            project_path: 项目根目录（包含成片/无字幕版等子文件夹）
            project_name: 项目名（用于 DB 记录和查询）
            workers: 并行线程数
            progress_callback: 可选回调函数，签名 callback(info_dict)
            opts: 可选 dict，包含 cp_folder / hardsub_folders / srt_folder /
                  opt_blackframes / opt_hardsubs / opt_duration / sub_region /
                  workers。如果传入且包含 cp_folder，则跳过自动检测。
            folder_layout: 可选，预设的 folder_layout（来自 auto_detect_folders）。

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

        # 1. 优先用传入的 folder_layout；否则自动检测
        if not folder_layout:
            folder_layout = self._detect_folder_layout(project_path)
        # 2. 用 opts 覆盖 folder_layout 中的版本选择
        if opts:
            if opts.get('cp_folder'):
                folder_layout['cp_folder'] = opts['cp_folder']
            if opts.get('hardsub_folders') is not None:
                folder_layout['hardsub_folders'] = list(opts['hardsub_folders'])
            if opts.get('srt_folder') is not None:
                folder_layout['srt_folders'] = [opts['srt_folder']] if opts['srt_folder'] else []
            if 'workers' in opts:
                workers = int(opts['workers'] or workers)

        cp_folder = folder_layout.get('cp_folder')
        if not cp_folder:
            logger.error("未能识别成片文件夹，请检查目录结构: %s", project_path)
            return False

        # 把 opts 合并进去（worker 再用）
        merged_opts = dict(opts) if opts else {}
        merged_opts.setdefault('workers', workers)

        thread = threading.Thread(
            target=self._run_worker,
            args=(project_path, project_name, folder_layout,
                  workers, progress_callback, merged_opts),
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

    def get_status(self, project_name):
        """查询项目当前质检实时状态（前端 /qa_status 调用）。

        返回结构匹配前端 qa.js 期望:
            {
              'is_running': bool,
              'progress': 0-100,
              'current_video': str,
              'total': int,
              'done': int,
              'status': 'running'|'done'|'cancelled'|'error'|'idle',
              'results': [...]  # 实时结果列表（部分进度）
            }
        """
        running = self.is_running(project_name)

        # 先消费进度队列里堆积的消息，更新 _latest_progress
        self._drain_progress_queue(project_name)

        with self._progress_lock:
            progress = dict(self._latest_progress.get(project_name) or {})

        if not progress:
            # 没有运行中的进度数据 → 尝试从 DB 读取最近一次记录
            run = self.status(project_name)
            if run:
                return {
                    'is_running': running,
                    'status': run.get('status', 'idle'),
                    'progress': 100 if run.get('status') == 'done' else 0,
                    'current_video': '',
                    'total': run.get('total', 0) or 0,
                    'done': run.get('total', 0) or 0,
                    'passed': run.get('passed', 0) or 0,
                    'warnings': run.get('warnings', 0) or 0,
                    'failed': run.get('failed', 0) or 0,
                    'results': [],
                }
            return {
                'is_running': running,
                'status': 'idle',
                'progress': 0,
                'current_video': '',
                'total': 0,
                'done': 0,
                'results': [],
            }

        progress['is_running'] = running
        return progress

    def _drain_progress_queue(self, project_name):
        """非阻塞地把进度队列里所有消息合并到 _latest_progress。"""
        q = self._progress_queues.get(project_name)
        if q is None:
            return
        latest = None
        while True:
            try:
                latest = q.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
        if latest is not None:
            with self._progress_lock:
                self._latest_progress[project_name] = latest

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
                   workers, progress_callback, merged_opts=None):
        """后台工作线程。merged_opts 是 Web 端传入的所有选项（含检测项、版本选择、sub_region 等）。

        断点续检 / checkpoint / extra_data（报告需要）逻辑完全照搬独立工具 process_thread。
        """
        run_id = None
        cancel_token = self._cancel_tokens.get(project_name)
        progress_q = self._progress_queues.get(project_name)
        t_start = time.perf_counter()
        merged_opts = merged_opts or {}

        try:
            # 延迟导入，避免循环依赖（qa_toolkits 顶部已经 import detection）
            import qa_toolkits

            cp_folder = folder_layout['cp_folder']
            hardsub_folders = folder_layout.get('hardsub_folders', [cp_folder])
            srt_folder = ((folder_layout.get('srt_folders') or [None])[0]
                          if not merged_opts.get('srt_folder') else merged_opts['srt_folder'])

            # opts 以 merged_opts 为基础（已包含检测项复选 / sub_region / hardsub_folders）
            opts = dict(merged_opts)
            opts.setdefault('cp_folder', cp_folder)
            opts.setdefault('hardsub_folders', hardsub_folders)
            opts.setdefault('srt_folder', srt_folder)
            opts.setdefault('opt_blackframes', True)
            opts.setdefault('opt_hardsubs', True)
            opts.setdefault('opt_duration', True)
            opts.setdefault('workers', workers)

            # 文件数量一致性校验（完全照搬独立工具 process_thread 顶部逻辑）
            all_video_folders = [cp_folder]
            for f in opts['hardsub_folders']:
                if f and f not in all_video_folders:
                    all_video_folders.append(f)
            file_counts = {}
            for folder in all_video_folders:
                try:
                    files = os.listdir(os.path.join(project_path, folder))
                except OSError:
                    files = []
                file_counts[folder] = sum(1 for f in files if f.endswith(VIDEO_EXTS))
            srt_count = 0
            if srt_folder:
                try:
                    files = os.listdir(os.path.join(project_path, srt_folder))
                except OSError:
                    files = []
                srt_count = sum(1 for f in files if f.endswith(SRT_EXTS))
            all_vals = list(file_counts.values()) + ([srt_count] if srt_folder else [])
            consistent = (len(set(all_vals)) == 1) if all_vals else True

            # 视频文件列表
            try:
                cp_files = [f for f in os.listdir(os.path.join(project_path, cp_folder))
                            if f.endswith(VIDEO_EXTS)]
            except OSError:
                cp_files = []
            cp_files.sort(key=detection.natural_sort_key)
            video_files = cp_files
            total = len(video_files)

            run_id = db.create_qa_run(project_name, started_at=_now(),
                                      status='running')
            logger.info("qa_run 创建成功: id=%d project=%s", run_id, project_name)

            progress_data = {
                'project_name': project_name,
                'status': 'running',
                'progress': 0,
                'current_video': '',
                'total': total,      # 已在上方算出
                'done': 0,
                'passed': 0,
                'warnings': 0,
                'failed': 0,
                'results': [],
                'log': [f"文件数量: {json.dumps(file_counts, ensure_ascii=False)}"
                        + (f", 字幕: {srt_count}" if srt_folder else "")],
            }
            if not consistent:
                progress_data['log'].append("⚠ 文件数量不一致!")
            else:
                progress_data['log'].append(
                    f"✓ 文件数量一致: {all_vals[0] if all_vals else 0}个")
            progress_data['log'].append(f"共 {total} 个视频待检")
            self._emit(progress_q, progress_callback, progress_data)

            if total == 0:
                # 无视频，直接结束
                folder_info = {'cp_folder': cp_folder, 'all_video_folders': all_video_folders,
                               'width': None, 'height': None}
                self._finalize_run(
                    run_id, project_name, project_path, cancel_token,
                    progress_q, progress_callback, progress_data,
                    [], folder_info, t_start, file_counts, srt_count,
                    consistent, all_video_folders, srt_folder, workers,
                )
                return

            # === 断点续检：加载已有 checkpoint ===
            checkpoint = qa_toolkits.load_checkpoint(project_path, opts=opts)
            pending_videos = []
            results = []
            skip_count = 0
            for vfile in video_files:
                vname = os.path.splitext(vfile)[0]
                if vname in checkpoint:
                    results.append(checkpoint[vname])
                    skip_count += 1
                else:
                    pending_videos.append(vfile)

            if skip_count > 0:
                progress_data['log'].append(
                    f"⏭ 断点续检：{skip_count}/{total} 已跳过（{total - skip_count} 待检）")
                results.sort(key=lambda r: detection.natural_sort_key(r.get('video', '')))
                for r in results:
                    self._persist_result(run_id, r, folder_layout)
                progress_data['results'] = self._to_public_results(results, folder_layout)
                progress_data['done'] = skip_count
                progress_data['passed'] = sum(1 for r in results if r.get('status') == 'pass')
                progress_data['warnings'] = sum(1 for r in results if r.get('status') == 'warn')
                progress_data['failed'] = sum(1 for r in results if r.get('status') == 'fail')
                if total > 0:
                    progress_data['progress'] = round(skip_count * 100 / total, 1)
                self._emit(progress_q, progress_callback, progress_data)

            cache = detection.VideoInfoCache()
            partial_results = list(results)  # 断点的 + 新测的

            def _on_progress(completed, total, pct):
                # completed 只含「本轮」检测到的数量；加上 skip_count 才是 UI 进度
                done_abs = skip_count + completed
                progress_data['progress'] = round(pct, 1)
                progress_data['done'] = done_abs
                progress_data['total'] = total
                progress_data['current_video'] = progress_data.get('_last_video', '')
                elapsed_here = time.perf_counter() - t_start
                avg = elapsed_here / max(done_abs, 1)
                remaining = max(0, (total - done_abs) * avg)
                progress_data['eta'] = round(remaining, 0)
                progress_data['elapsed'] = round(elapsed_here, 1)
                self._emit(progress_q, progress_callback, progress_data)

            def _on_result(result):
                partial_results.append(result)
                # 每拿到一条都实时更新 pass/warn/fail 计数，供进度条旁展示
                p = sum(1 for r in partial_results if r.get('status') == 'pass')
                w = sum(1 for r in partial_results if r.get('status') == 'warn')
                f = sum(1 for r in partial_results if r.get('status') == 'fail')
                progress_data['passed'] = p
                progress_data['warnings'] = w
                progress_data['failed'] = f
                progress_data['results'] = self._to_public_results(
                    partial_results, folder_layout)
                progress_data['_last_video'] = result.get('video', '')
                progress_data['current_video'] = result.get('video', '')
                self._persist_result(run_id, result, folder_layout)

            def _on_log(text):
                logger.info("[%s] %s", project_name, text)
                # 让 Web 端拿到日志流（独立工具 log window 的等价物）
                log_list = progress_data.setdefault('log', [])
                log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] {text}")
                # 控制日志长度，免得无限增长
                if len(log_list) > 200:
                    progress_data['log'] = log_list[-200:]

            folder_info = {}
            if pending_videos and (not cancel_token or not cancel_token.cancelled):
                batch_ret = detection.run_detection_batch(
                    base=project_path,
                    opts=opts,
                    cache=cache,
                    cancel_token=cancel_token,
                    on_progress=_on_progress,
                    on_result=_on_result,
                    on_log=_on_log,
                )
                if isinstance(batch_ret, tuple) and len(batch_ret) == 2:
                    new_results, folder_info = batch_ret
                else:
                    new_results = batch_ret or []
                results = results + new_results
            else:
                # 全部来自 checkpoint，没跑 detection 批；取第一个视频信息凑 folder_info
                first_video = os.path.join(project_path, cp_folder, video_files[0])
                info = detection.get_video_info(first_video)
                if info:
                    sub_y_s = getattr(detection, 'SUB_Y_RATIO_START', 0.68)
                    sub_y_e = getattr(detection, 'SUB_Y_RATIO_END', 0.83)
                    folder_info = {
                        'cp_folder': cp_folder,
                        'hardsub_folders': opts['hardsub_folders'],
                        'all_video_folders': all_video_folders,
                        'width': info.get('width'),
                        'height': info.get('height'),
                        'fps': info.get('fps'),
                        'codec': info.get('codec'),
                        'sub_y': int(info['height'] * sub_y_s),
                        'sub_h': int(info['height'] * (sub_y_e - sub_y_s)),
                        'sub_x': 0,
                        'sub_w': info.get('width'),
                    }

            results.sort(key=lambda r: detection.natural_sort_key(r.get('video', '')))

            # 保存 checkpoint
            if results:
                qa_toolkits.save_checkpoint(project_path, results, opts=opts)

            self._finalize_run(
                run_id, project_name, project_path, cancel_token,
                progress_q, progress_callback, progress_data,
                results, folder_info, t_start, file_counts, srt_count,
                consistent, all_video_folders, srt_folder, workers,
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

    # 报告生成后把 (results, extra_data, output_path) 缓存下来，供 /qa_report 路由直接取
    # 结构: {project_name: {results, extra_data, html_path, json_path, workers, project_path}}
    _report_cache = {}

    def _finalize_run(self, run_id, project_name, project_path, cancel_token,
                      progress_q, progress_callback, progress_data,
                      results, folder_info, t_start, file_counts, srt_count,
                      consistent, all_video_folders, srt_folder, workers):
        """把质检收尾逻辑抽取出来（DB 更新、写 JSON、报告缓存、通知 done）。"""
        import qa_toolkits

        total = len(results)
        passed = sum(1 for r in results if r.get('status') == 'pass')
        warnings = sum(1 for r in results if r.get('status') == 'warn')
        failed = sum(1 for r in results if r.get('status') == 'fail')
        elapsed = round(time.perf_counter() - t_start, 2)

        # 把 folder_info 合并 all_video_folders 等字段
        folder_info = dict(folder_info or {})
        folder_info.setdefault('cp_folder', (progress_data or {}).get('cp_folder'))
        folder_info['all_video_folders'] = list(all_video_folders)
        folder_info['batch_total_seconds'] = elapsed
        folder_info['batch_videos_completed'] = total

        extra_data = {
            'file_counts': file_counts,
            'srt_count': srt_count,
            'consistent': consistent,
            'folder_info': folder_info,
            'srt_folder': srt_folder,
            'cp_folder': folder_info.get('cp_folder'),
        }

        summary = {
            'total': total,
            'passed': passed,
            'warnings': warnings,
            'failed': failed,
            'elapsed_seconds': elapsed,
            'folders': folder_info,
            'videos': [
                {'video': r.get('video'), 'status': r.get('status'),
                 'issues': r.get('issues', []), 'details': r.get('details', '')}
                for r in results
            ],
        }

        run_status = 'cancelled' if (cancel_token and cancel_token.cancelled) else 'done'
        if run_id is not None:
            try:
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
            except Exception as db_err:
                logger.error("更新 qa_run 失败: %s", db_err)

        # 写入 qa_result_*.json（供 /api/project/<name>/qa_result 读）
        result_json_path = self._write_qa_result_json(
            project_name, project_path, results, folder_info,
            passed, warnings, failed, elapsed)

        # 生成 HTML 报告并缓存路径（独立工具 _on_done 的等价物）
        html_path = None
        try:
            html_path = qa_toolkits.generate_report_html(
                project_path, project_name, results, total,
                extra_data=extra_data, workers=workers,
            )
        except Exception as rep_err:
            logger.error("生成 HTML 报告失败: %s", rep_err)

        # 缓存报告源数据（/qa_report HTML / JSON 下载路由要用）
        with self._status_lock:
            self._report_cache[project_name] = {
                'results': results,
                'extra_data': extra_data,
                'html_path': html_path,
                'qa_result_file': result_json_path,
                'workers': workers,
                'project_path': project_path,
                'project_name': project_name,
                'timestamp': _now(),
            }

        progress_data['status'] = run_status
        progress_data['progress'] = 100
        progress_data['total'] = total
        progress_data['done'] = total
        progress_data['passed'] = passed
        progress_data['warnings'] = warnings
        progress_data['failed'] = failed
        progress_data['results'] = self._to_public_results(results, folder_info)
        progress_data['qa_result_file'] = result_json_path
        progress_data['report_html'] = html_path
        progress_data.pop('_last_video', None)
        # 最终日志
        progress_data.setdefault('log', []).append(
            f"✅ 检测完成  {passed}通过, {warnings}警告, {failed}失败  耗时{elapsed:.1f}s")
        if html_path:
            progress_data['log'].append(f"报告已生成: {html_path}")
        self._emit(progress_q, progress_callback, progress_data)

        # ===== 质检完成自动流转工作流状态 =====
        # 仅正常完成时流转（取消/异常不改变状态）
        if run_status == 'done':
            self._auto_advance_workflow(project_name, passed, failed)

        logger.info(
            "质检完成: project=%s status=%s total=%d pass=%d warn=%d fail=%d elapsed=%.1fs",
            project_name, run_status, total, passed, warnings, failed, elapsed
        )

    def _auto_advance_workflow(self, project_name, passed, failed):
        """质检完成后自动推进项目工作流状态：
        - 全部通过(failed==0) → 流转到"待交付"（进入交付环节）
        - 有失败(failed>0)   → 流转到"修改中"（需修复后重新质检）
        """
        try:
            proj = db.get_project(project_name)
            if not proj:
                return
            cur = str(proj.get("custom_status") or "").strip()
            # 只在"质检中/待质检"状态推进，避免覆盖用户手动设置的其他状态
            if cur not in ("质检中", "待质检"):
                return
            target = "待交付" if failed == 0 else "修改中"
            db.update_project_status(
                project_name, custom_status=target,
                sync_progress="质检%s，自动流转到%s" % ("通过" if failed == 0 else "未通过", target))
            try:
                db.add_sync_log(
                    project_name, "质检完成自动流转", "qa",
                    status="info",
                    message="质检%s (%d失败)，状态 %s → %s" % (
                        "通过" if failed == 0 else "未通过", failed, cur, target))
            except Exception:
                pass
            logger.info("质检自动流转: %s %s -> %s (fail=%d)", project_name, cur, target, failed)
        except Exception as e:
            logger.warning("质检自动流转失败: %s", e)

    def get_last_result(self, project_name):
        """返回某个项目最近一次质检的结果缓存（含报告路径）。

        返回:
            {results, extra_data, html_path, qa_result_file, workers,
             project_path, project_name, timestamp} 或 None
        """
        with self._status_lock:
            cached = self._report_cache.get(project_name)
            if cached:
                return dict(cached)
        return None

    # ================================================================
    # 工具函数
    # ================================================================

    def _emit(self, progress_q, callback, data):
        """把进度数据推到队列、回调、以及 _latest_progress 内存镜像。

        _latest_progress 让 get_status() 无需消费队列即可返回最新进度。
        """
        snapshot = dict(data)
        # 内存镜像：供 /qa_status 直接读取
        project_name = snapshot.get('project_name')
        if project_name:
            with self._progress_lock:
                self._latest_progress[project_name] = snapshot

        if progress_q is not None:
            try:
                progress_q.put_nowait(snapshot)
            except queue.Full:
                try:
                    progress_q.get_nowait()
                    progress_q.put_nowait(snapshot)
                except Exception:
                    pass
        if callback is not None:
            try:
                callback(snapshot)
            except Exception as e:
                logger.debug("progress_callback 抛异常: %s", e)

    @staticmethod
    def _write_qa_result_json(project_name, project_path, results, folder_layout,
                              passed, warnings, failed, elapsed):
        """把最终检测结果写入 %TEMP%/qa_result_{project_name}_{ts}.json

        与参考实现 视频质检工具.pyw 第 2133-2152 行一致，
        供 app.py 的 /api/project/<name>/qa_result 路由读取。
        """
        try:
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 文件名去掉非法字符（路径分隔符等）
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', str(project_name))
            out_path = os.path.join(
                tempfile.gettempdir(),
                f"qa_result_{safe_name}_{ts_str}.json"
            )
            payload = {
                "project": project_path,
                "project_name": project_name,
                "generated_at": datetime.now().isoformat(timespec='seconds'),
                "total": len(results),
                "passed": passed,
                "warnings": warnings,
                "failed": failed,
                "elapsed_seconds": round(elapsed, 2),
                "results": results,
                "folders": folder_layout,
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info("qa_result JSON 已写入: %s", out_path)
            return out_path
        except Exception as e:
            logger.error("写入 qa_result JSON 失败: %s", e)
            return None

    @staticmethod
    def _to_public_results(results, folder_layout):
        cp_folder = folder_layout.get('cp_folder', '')
        out = []
        for r in results:
            video = r.get('video', '')
            # fps 从 fps_check 取（detection.py 把帧率放在 r['fps_check'][folder]）
            fps_check = r.get('fps_check', {}) or {}
            fps_val = fps_check.get(cp_folder, 0) or 0
            # 分辨率从 folder_layout 的 width/height 取（detection 在 batch 入口已探得）
            width = folder_layout.get('width')
            height = folder_layout.get('height')
            resolution = f"{width}x{height}" if width and height else ''

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
            # fps 从 fps_check 取，resolution 从 folder_layout 的 width/height 取
            fps_check = result.get('fps_check', {}) or {}
            fps = fps_check.get(cp_folder, 0) or 0.0
            if not fps:
                for fv in fps_check.values():
                    if fv:
                        fps = fv
                        break
            width = folder_layout.get('width')
            height = folder_layout.get('height')
            resolution = f"{width}x{height}" if width and height else ''

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
