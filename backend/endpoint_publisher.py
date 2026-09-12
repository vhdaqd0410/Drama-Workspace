# -*- coding: utf-8 -*-
r"""B2：主端定期把自己的地址写到组内 NAS 的 _协作/endpoint.json，
供组员端「自动检测」读取。

写入内容：host / port / group_root / api_secret / updated
（组内盘组员有读写权限，且是同组内部共享，可接受）

安全性说明：api_secret 写入组内 NAS 意味着有组内盘访问权的人能拿到主端密钥。
组长明确要求「组员零配置 + 自动检测」，这是该取舍的直接后果。
若日后想更严，可改为只写 host/port，密钥改由组长单独发给组员。
"""
import os
import json
import socket
import threading
import time
import logging

logger = logging.getLogger("endpoint_publisher")

_INTERVAL = 120      # 秒


def _local_ip():
    """取本机在局域网中的 IP（不会被路由到外网的情况下最准）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def publish_once(config):
    """写一次 endpoint.json。返回 (ok, path_or_msg)。"""
    try:
        nas = config.get("nas", {}) or {}
        group_root = nas.get("group_root") or ""
        if not group_root:
            return False, "未配置 group_root"
        if not os.path.isdir(group_root):
            return False, "组内 NAS 不可访问: %s" % group_root
        web = config.get("web", {}) or {}
        d = {
            "host": _local_ip(),
            "port": web.get("port", 8089),
            "group_root": group_root,
            "api_secret": web.get("api_secret", ""),
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        col = os.path.join(group_root, "_协作")
        os.makedirs(col, exist_ok=True)
        p = os.path.join(col, "endpoint.json")
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True, p
    except Exception as e:
        return False, str(e)


def start_publisher(config, interval=_INTERVAL):
    """后台线程定期发布。幂等。"""
    if getattr(start_publisher, "_started", False):
        return
    start_publisher._started = True

    def _loop():
        while True:
            ok, info = publish_once(config)
            if ok:
                logger.info("已发布主端地址: %s", info)
            else:
                logger.warning("发布主端地址失败: %s", info)
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True).start()
    print("[OK] endpoint_publisher(主端地址发布) 已启动")
