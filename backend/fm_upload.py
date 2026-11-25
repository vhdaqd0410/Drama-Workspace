# -*- coding: utf-8 -*-
"""分秒帧上传状态跟踪（供工作台桌面端使用，可独立单测）。

背景：
  上传是分秒帧网页里发起的腾讯云 COS 分片上传，发生在 WebView2 内部，
  宿主进程拿不到网络流。只能由页面内注入的 JS hook XHR.upload.onprogress，
  把 {active, loaded, total} 回传到这里。

本模块负责：
  1. 维护「当前是否在上传」（用于关闭窗口时的保护提示）
  2. 判定「上传是否真的结束」——分片之间 active 会短暂归零，
     所以要通过一段静默期确认，否则会疯狂误报"上传完成"。
"""
import threading
import time

# active     正在上传的任务数
# loaded/total  当前进度字节
# in_flight  是否处于上传会话中（含刚结束的宽限期）
# last_report  最近一次回传时间
_state = {
    "active": 0,
    "loaded": 0,
    "total": 0,
    "in_flight": False,
    "last_report": 0.0,
}

_lock = threading.Lock()
_done_timer = None
_done_callback = None

# 分片间隙静默多久才认为上传真的结束（秒）
DONE_QUIET_SECONDS = 4.0


def set_done_callback(fn):
    """注册「上传结束」回调（参数为汇总文案）。"""
    global _done_callback
    _done_callback = fn


def snapshot():
    with _lock:
        return dict(_state)


def is_uploading():
    """当前是否应该阻止关闭窗口。

    active>0 一定有任务；in_flight 覆盖刚结束的宽限期，
    避免分片间隙里点关闭导致其实还在传。
    """
    with _lock:
        return bool(_state["active"] > 0 or _state["in_flight"])


def reset():
    """窗口关闭后清空状态，避免残留 in_flight 让下次关闭一直被拦。"""
    global _done_timer
    with _lock:
        _state.update({"active": 0, "loaded": 0, "total": 0,
                       "in_flight": False, "last_report": 0.0})
        t = _done_timer
        _done_timer = None
    if t is not None:
        try:
            t.cancel()
        except Exception:
            pass


def _fire_done():
    """静默期到点：确认真的结束，触发一次完成回调。"""
    global _done_timer
    with _lock:
        if _state["active"] > 0:
            return                      # 又开始了，不是真完成
        if not _state["in_flight"] and _state["last_report"] == 0.0:
            return                      # 从没开始过
        _state["in_flight"] = False
        _done_timer = None
        mb = (_state["loaded"] or 0) / (1024.0 * 1024.0)
    cb = _done_callback
    if cb is not None:
        try:
            cb("上传已结束，本次共传输约 %.1f MB" % mb)
        except Exception:
            pass


def report(active, loaded, total):
    """接收页面回传的上传进度。

    返回 dict：{ok, done_scheduled}
    """
    global _done_timer
    try:
        active = int(active or 0)
        loaded = int(loaded or 0)
        total = int(total or 0)
    except Exception:
        return {"ok": False}

    prev_active = 0
    cancel_timer = None

    with _lock:
        prev_active = _state["active"]
        _state["active"] = active
        _state["loaded"] = loaded
        _state["total"] = total
        _state["last_report"] = time.time()

        if active > 0:
            _state["in_flight"] = True
            # 新上传开始 → 取消待发的完成提醒（分片间隙会短暂归零）
            cancel_timer = _done_timer
            _done_timer = None

    if cancel_timer is not None:
        try:
            cancel_timer.cancel()
        except Exception:
            pass

    # 从"有上传"归零 → 排一个静默确认
    if active == 0 and prev_active > 0:
        t = threading.Timer(DONE_QUIET_SECONDS, _fire_done)
        t.daemon = True
        with _lock:
            old = _done_timer
            _done_timer = t
        if old is not None:
            try:
                old.cancel()
            except Exception:
                pass
        t.start()
        return {"ok": True, "done_scheduled": True}

    return {"ok": True, "done_scheduled": False}