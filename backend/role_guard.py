# -*- coding: utf-8 -*-
"""组员端权限闸门（白名单，失败时拒绝）。

设计原则：
  - 白名单制：只有明确列出的端点组员可达，其余一律 403。
    黑名单在实测中反复漏项（/api/team、/api/projects/light、/api/search…），
    因为黑名单的失效方向是「放行」，不可接受。
  - 组员能力边界：看组内项目、看进度、打勾、管自己的待办、创建本地项目、预览成片。
  - 组长（主端密钥）不经过本闸门，行为完全不变。
"""
import re

# ---------- 精确端点（METHOD + 路径正则）----------
# 组员允许的 (方法, 正则) 列表。方法为 "*" 表示任意方法。
MEMBER_ALLOW = [
    ("GET", r"^/api/health$"),
    ("GET", r"^/api/status$"),
    ("GET", r"^/api/sse$"),

    # 项目列表 / 基础信息
    ("GET", r"^/api/projects$"),
    ("GET", r"^/api/project_months$"),
    ("GET", r"^/api/notifications$"),
    ("GET", r"^/api/settings$"),

    # 协作（打勾、摘要、通知、自身信息）
    ("GET", r"^/api/collab/(me|summary|checks|notices)$"),
    ("POST", r"^/api/collab/check$"),

    # 项目详情与进度
    ("GET", r"^/api/project/[^/]+$"),
    ("GET", r"^/api/project/[^/]+/episodes_status$"),
    ("GET", r"^/api/project/[^/]+/timeline$"),
    ("GET", r"^/api/project/[^/]+/output_dir$"),
    ("GET", r"^/api/project/[^/]+/source_dir$"),
    ("GET", r"^/api/project/[^/]+/local_project_progress$"),
    ("GET", r"^/api/project/[^/]+/local_materials$"),

    # 待办（组员可看/管自己的待办）
    ("GET", r"^/api/project/[^/]+/todos$"),
    ("POST", r"^/api/project/[^/]+/todos$"),
    ("PUT", r"^/api/project/[^/]+/todos/\d+$"),
    ("GET", r"^/api/todos/global$"),
    ("GET", r"^/api/todos/board$"),

    # 创建本地项目（组员核心能力）
    ("POST", r"^/api/project/[^/]+/create_local_project$"),

    # 预览 / 缩略图 / 文件流（只读）
    ("GET", r"^/api/preview/"),
    ("GET", r"^/api/thumbnail"),
    ("GET", r"^/api/frame/"),
    ("GET", r"^/api/file_stream/"),

    # 分秒帧（只读跳转）
    ("GET", r"^/api/fenmiaozhen/config$"),
    ("GET", r"^/api/fenmiaozhen/link/"),
]

# 组员绝不允许的方法（即便路径碰巧匹配）
MEMBER_FORBID_METHODS = ("DELETE", "PATCH")


def member_denied(method, path):
    """组员请求是否应被拒绝。返回 (denied: bool, reason: str)。"""
    m = (method or "GET").upper()
    p = path or ""

    # 白名单优先判定
    for allow_m, pat in MEMBER_ALLOW:
        if allow_m != "*" and allow_m != m:
            continue
        try:
            if re.match(pat, p):
                # 命中白名单，但禁止的方法仍拦
                if m in MEMBER_FORBID_METHODS:
                    return True, "组员无权执行 %s" % m
                return False, ""
        except re.error:
            continue

    return True, "组员无权访问: %s %s" % (m, p)
