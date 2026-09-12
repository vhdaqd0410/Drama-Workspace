# -*- coding: utf-8 -*-
"""组员端身份认证（member token）。

设计：
  - 主端沿用 config.yaml 的 web.api_secret（组长权限）
  - 组员用 team_members.token 里的独立令牌（组员权限）
  - 两者在同一鉴权关口并存，互不影响；主端行为完全不变

令牌缓存 30 秒，避免每个请求都查库。
"""
import time
import logging

logger = logging.getLogger("member_auth")

# 鉴权请求头名（与 app.py 现有头名一致，单源定义避免写错）
AUTH_HEADER = 'X-API-KEY'

_CACHE = {}          # token -> member dict
_CACHE_TS = [0.0]
_TTL = 30.0


def reload_cache(db):
    """重新加载所有组员令牌。"""
    try:
        rows = db.list_members_ext() or []
    except Exception as e:
        logger.warning("加载成员列表失败: %s", e)
        rows = []
    _CACHE.clear()
    for r in rows:
        t = str(r.get("token") or "").strip()
        if t:
            _CACHE[t] = r
    _CACHE_TS[0] = time.time()
    return len(_CACHE)


def member_from_token(db, token):
    """按令牌取组员信息；无效返回 None。"""
    t = str(token or "").strip()
    if not t:
        return None
    if not _CACHE or (time.time() - _CACHE_TS[0]) > _TTL:
        reload_cache(db)
    return _CACHE.get(t)


def role_of(db, api_secret, credential):
    """判定请求身份。

    返回 (role, member)：
      ("lead",   None)  主端密钥
      ("member", {...}) 组员令牌
      (None,     None)  无效凭据
    """
    cred = str(credential or "").strip()
    if not cred:
        return None, None
    if api_secret and cred == api_secret:
        return "lead", None
    m = member_from_token(db, cred)
    if m:
        return "member", m
    return None, None


def new_token():
    """生成一个组员令牌。"""
    import secrets
    return "mb_" + secrets.token_urlsafe(24)
