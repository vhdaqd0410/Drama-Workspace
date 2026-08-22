# -*- coding: utf-8 -*-
"""单一版本号来源：所有入口（网页版 / 桌面版 / 托盘 / 日志）统一引用，避免各处硬编码漂移。"""
import os

VERSION = "3.2.0"
APP_NAME = "视频工作台"
APP_TITLE = "🎬 {} v{}".format(APP_NAME, VERSION)
MUTEX_NAME = "DramaWorkspace.SingleInstance.Mutex"   # 名称刻意与版本无关，避免升级后出现多实例
