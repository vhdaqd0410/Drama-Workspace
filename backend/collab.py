# -*- coding: utf-8 -*-
"""组员协作接口：打勾 / 进度矩阵 / 协作通知 / 成员令牌管理。

阶段定义（phase）：
  cut     剪辑完成   —— 项目状态 剪辑中 / 待审核
  revise  修改完成   —— 项目状态 审核中 / 修改中
  deliver 交付完成   —— 项目状态 待交付 / 待质检 / 已完成

打勾齐的判定：该阶段「应参与的人」全部打勾。
  cut/deliver 应参与人 = 项目分集(episode_plan)里出现过的所有剪辑师
  revise      应参与人 = 本轮修改范围(revision_scope)选中集数的负责人
                        （无范围记录时退回全员，避免死锁）
"""
import json
import logging

from flask import jsonify, request

import member_auth

logger = logging.getLogger("collab")

PHASES = ("cut", "revise", "deliver")
PHASE_LABEL = {"cut": "剪辑完成", "revise": "修改完成", "deliver": "交付完成"}
STATUS_PHASE = {
    "剪辑中": "cut",
    "待审核": "cut",
    "审核中": "revise",
    "修改中": "revise",
    "待交付": "deliver",
    "待质检": "deliver",
    "已完成": "deliver",
}


def _credential():
    return (request.headers.get(member_auth.AUTH_HEADER, "")
            or request.args.get("key", "")).strip()


def _identity(api_secret, db):
    """返回 (role, member_name)。"""
    role, m = member_auth.role_of(db, api_secret, _credential())
    return role, (m.get("name") if m else None)


def _episode_plan(proj):
    raw = proj.get("episode_plan") or "{}"
    try:
        plan = json.loads(raw) if isinstance(raw, str) else raw
        return plan if isinstance(plan, dict) else {}
    except Exception:
        return {}


def _phase_of_status(status):
    """状态 -> 阶段；无对应阶段返回 None。"""
    return STATUS_PHASE.get(str(status or "").strip())


def _round_for(phase, proj, db):
    """各阶段使用的轮次。

    cut / deliver: 恒为 1（一次性动作）
    revise       : 项目当前修改轮次（round=0 视为第 1 轮）
    """
    if phase == "revise":
        try:
            return max(1, int(proj.get("review_round") or 0))
        except Exception:
            return 1
    return 1


def _phase_active(phase, status, proj, db, round_no):
    """该阶段当前是否真的需要关注（决定卡片是否显示打勾条）。

    cut     : 剪辑中 / 待审核
    revise  : 修改中，或（审核中 且 本轮已有修改范围/打勾记录）
    deliver : 待交付 / 待质检 / 已完成
    """
    s = str(status or "").strip()
    if phase == "cut":
        return s in ("剪辑中", "待审核")
    if phase == "deliver":
        return s in ("待交付", "待质检", "已完成")
    if phase == "revise":
        if s == "修改中":
            return True
        if s == "审核中":
            # 本轮有修改范围或已有打勾，才算「修改已提交待复核」
            eps, _n = db.get_revision_scope(proj.get("name"), round_no)
            if eps:
                return True
            return db.count_checks(proj.get("name"), "revise", round_no) > 0
        return False
    return False


def _all_editors(proj):
    plan = _episode_plan(proj)
    eds = set()
    for _ep, ed in plan.items():
        s = str(ed or "").strip()
        if s:
            eds.add(s)
    return sorted(eds)


def _expected_editors(db, proj, phase, round_no):
    """该阶段应打勾的人。"""
    if phase == "revise":
        eps, _note = db.get_revision_scope(proj.get("name"), round_no)
        if eps:
            plan = _episode_plan(proj)
            eds = set()
            for ep in eps:
                ed = plan.get(str(ep)) or plan.get(ep)
                s = str(ed or "").strip()
                if s:
                    eds.add(s)
            if eds:
                return sorted(eds)
    return _all_editors(proj)


def _phase_state(db, proj, phase, round_no):
    """返回该阶段的完整状态：应参与/已打勾/是否齐。"""
    expected = _expected_editors(db, proj, phase, round_no)
    rows = db.get_project_checks(proj.get("name"), phase=phase, round_no=round_no)
    done_map = {}
    for r in rows:
        if int(r.get("done") or 0) == 1:
            done_map[str(r.get("editor"))] = r
    done = [e for e in expected if e in done_map]
    missing = [e for e in expected if e not in done_map]
    return {
        "phase": phase,
        "phase_label": PHASE_LABEL.get(phase, phase),
        "expected": expected,
        "done": done,
        "missing": missing,
        "all_done": bool(expected) and not missing,
        "round": int(round_no),
    }


def register_routes(app, db, sync_engine=None, api_secret=None):

    def _secret():
        if api_secret:
            return api_secret
        try:
            from app import _API_SECRET as s
            return s
        except Exception:
            return None

    # ---------- 身份 ----------

    @app.route("/api/collab/me", methods=["GET"])
    def collab_me():
        role, name = _identity(_secret(), db)
        return jsonify({"ok": True, "role": role or "none", "name": name})

    # ---------- 打勾 ----------

    @app.route("/api/collab/checks", methods=["GET"])
    def collab_checks():
        project = (request.args.get("project") or "").strip()
        if not project:
            return jsonify({"ok": False, "message": "缺少 project"}), 400
        proj = db.get_project(project)
        if not proj:
            return jsonify({"ok": False, "message": "项目不存在"}), 404
        status = proj.get("custom_status") or ""
        cur_phase = _phase_of_status(status)
        rnd = _round_for(cur_phase or "cut", proj, db)
        phases = {}
        for p in PHASES:
            prnd = _round_for(p, proj, db)
            st = _phase_state(db, proj, p, prnd)
            st["active"] = _phase_active(p, status, proj, db, prnd)
            phases[p] = st
        return jsonify({
            "ok": True,
            "project": project,
            "status": status,
            "current_phase": cur_phase,
            "review_round": rnd,
            "phases": phases,
        })

    @app.route("/api/collab/check", methods=["POST"])
    def collab_check():
        """打勾。body: {project, phase?, done?, note?}
        组员只能给自己打勾；组长可指定 editor。"""
        data = request.get_json(silent=True) or {}
        project = (data.get("project") or "").strip()
        if not project:
            return jsonify({"ok": False, "message": "缺少 project"}), 400
        proj = db.get_project(project)
        if not proj:
            return jsonify({"ok": False, "message": "项目不存在"}), 404

        role, my_name = _identity(_secret(), db)
        if role is None:
            return jsonify({"ok": False, "message": "未认证"}), 401

        phase = (data.get("phase") or "").strip() or _phase_of_status(proj.get("custom_status"))
        if phase not in PHASES:
            return jsonify({"ok": False, "message": "无效阶段: %s" % phase}), 400

        rnd = _round_for(phase, proj, db)
        # 组员：强制以自己的名义打勾（防冒名）
        editor = (data.get("editor") or "").strip() if role == "lead" else my_name
        if not editor:
            return jsonify({"ok": False, "message": "无法确定操作人"}), 400

        done = 1 if data.get("done", True) else 0
        db.set_project_check(project, editor, phase, round_no=rnd,
                             done=done, note=data.get("note") or "",
                             updated_by=my_name or editor)

        state = _phase_state(db, proj, phase, rnd)
        notice = None
        if done and state["all_done"]:
            # 全员完成 → 生成协作通知（组长可见），并 SSE 推送
            db.add_collab_notice(
                project, "check_done", phase=phase, round_no=rnd,
                actor=my_name or editor,
                detail="%s 全部完成（%d 人）" % (
                    PHASE_LABEL.get(phase, phase), len(state["expected"])))
            notice = "all_done"
            if sync_engine is not None:
                try:
                    sync_engine._sse_publish({
                        "type": "collab", "project": project,
                        "phase": phase, "round": rnd, "status": "all_done",
                    })
                except Exception:
                    pass
        else:
            db.add_collab_notice(
                project, "check_one", phase=phase, round_no=rnd,
                actor=my_name or editor,
                detail="%s 打勾 %s" % (editor, PHASE_LABEL.get(phase, phase)))
            if sync_engine is not None:
                try:
                    sync_engine._sse_publish({
                        "type": "collab", "project": project,
                        "phase": phase, "round": rnd, "status": "one",
                        "editor": editor,
                    })
                except Exception:
                    pass

        return jsonify({"ok": True, "state": state, "notice": notice})

    # ---------- 批量摘要（项目卡片直出打勾用） ----------

    @app.route("/api/collab/summary", methods=["GET"])
    def collab_summary():
        """返回「进行中项目的打勾摘要」，供项目卡片直接渲染打勾按钮。

        只统计有 custom_status 且有分集分配的项目（通常十几个），避免全量扫描。
        组员视角：额外返回 mine 字段（自己是否在应参与名单、是否已打勾），
                  并且只返回与自己相关的项目。
        """
        role, my_name = _identity(_secret(), db)
        if role is None:
            return jsonify({"ok": False, "message": "未认证"}), 401
        try:
            projs = db.get_all_projects() or []
        except Exception as e:
            logger.warning("读取项目失败: %s", e)
            projs = []

        out = {}
        for p in projs:
            status = str(p.get("custom_status") or "").strip()
            if not status or status == "已完成":
                continue
            plan = _episode_plan(p)
            if not plan:
                continue
            phase = _phase_of_status(status)
            rnd = _round_for(phase or "cut", p, db)
            if not _phase_active(phase, status, p, db, rnd):
                continue
            st = _phase_state(db, p, phase, rnd)
            if not st["expected"]:
                continue
            if role == "member" and my_name not in st["expected"]:
                continue    # 组员只看与自己相关的项目
            item = {
                "phase": phase,
                "phase_label": st["phase_label"],
                "expected": st["expected"],
                "done": st["done"],
                "missing": st["missing"],
                "all_done": st["all_done"],
                "round": rnd,
                "status": status,
            }
            if role == "member":
                item["mine"] = {
                    "in_scope": my_name in st["expected"],
                    "done": my_name in st["done"],
                    "name": my_name,
                }
            out[p.get("name")] = item

        return jsonify({"ok": True, "role": role, "projects": out,
                        "count": len(out)})

    # ---------- 进度矩阵（组长） ----------

    @app.route("/api/collab/progress", methods=["GET"])
    def collab_progress():
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        rows = []
        try:
            projs = db.get_all_projects() or []
        except Exception as e:
            logger.warning("读取项目失败: %s", e)
            projs = []
        for p in projs:
            status = str(p.get("custom_status") or "").strip()
            if not status or status == "已完成":
                continue
            phase = _phase_of_status(status)
            rnd = _round_for(phase or "cut", p, db)
            if not _phase_active(phase, status, p, db, rnd):
                continue    # 当前阶段无需关注（如审核中且无修改记录）
            st = _phase_state(db, p, phase, rnd)
            if not st["expected"]:
                continue    # 没分配人的项目不展示
            rows.append({
                "project": p.get("name"),
                "status": status,
                "phase": phase,
                "phase_label": st["phase_label"],
                "round": rnd,
                "expected": st["expected"],
                "done": st["done"],
                "missing": st["missing"],
                "all_done": st["all_done"],
            })
        rows.sort(key=lambda r: (r["all_done"], r["project"] or ""))
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})

    # ---------- 通知 ----------

    @app.route("/api/collab/notices", methods=["GET"])
    def collab_notices():
        include_acked = (request.args.get("all") or "") == "1"
        rows = db.list_collab_notices(include_acked=include_acked, limit=200)
        return jsonify({"ok": True, "notices": rows,
                        "unread": db.count_unacked_notices()})

    @app.route("/api/collab/notice_ack", methods=["POST"])
    def collab_notice_ack():
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        data = request.get_json(silent=True) or {}
        nid = data.get("id")
        if nid:
            db.ack_collab_notice(notice_id=nid)
        else:
            db.ack_collab_notice(project_name=data.get("project") or None,
                                 kind=data.get("kind") or None)
        return jsonify({"ok": True, "unread": db.count_unacked_notices()})

    # ---------- 修改范围 ----------

    @app.route("/api/collab/revision_scope", methods=["GET", "POST"])
    def collab_revision_scope():
        if request.method == "GET":
            project = (request.args.get("project") or "").strip()
            rnd = request.args.get("round")
            proj = db.get_project(project)
            if not proj:
                return jsonify({"ok": False, "message": "项目不存在"}), 404
            rnd = int(rnd) if rnd else max(1, int(proj.get("review_round") or 0))
            eps, note = db.get_revision_scope(project, rnd)
            plan = _episode_plan(proj)
            detail = [{"episode": e, "editor": plan.get(str(e)) or plan.get(e) or ""}
                      for e in eps]
            return jsonify({"ok": True, "round": rnd, "episodes": eps,
                            "detail": detail, "note": note})

        role, name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        data = request.get_json(silent=True) or {}
        project = (data.get("project") or "").strip()
        proj = db.get_project(project)
        if not proj:
            return jsonify({"ok": False, "message": "项目不存在"}), 404
        eps = data.get("episodes") or []
        if not isinstance(eps, list):
            return jsonify({"ok": False, "message": "episodes 需为数组"}), 400
        rnd = int(data.get("round") or max(1, int(proj.get("review_round") or 0)))
        db.set_revision_scope(project, rnd, eps, note=data.get("note") or "")
        plan = _episode_plan(proj)
        detail = [{"episode": e, "editor": plan.get(str(e)) or plan.get(e) or ""}
                  for e in eps]
        return jsonify({"ok": True, "round": rnd, "episodes": eps,
                        "detail": detail, "by": name})

    # ---------- 成员令牌管理（组长） ----------

    @app.route("/api/collab/members", methods=["GET"])
    def collab_members():
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        rows = db.list_members_ext() or []
        out = []
        for r in rows:
            out.append({
                "name": r.get("name"),
                "role": r.get("role"),
                "title": r.get("title") or "",
                "department": r.get("department") or "",
                "client_role": r.get("client_role") or "lead",
                "has_token": bool(str(r.get("token") or "").strip()),
                "token": r.get("token") or "",
            })
        return jsonify({"ok": True, "members": out})

    @app.route("/api/collab/member_token", methods=["POST"])
    def collab_member_token():
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "message": "缺少 name"}), 400
        token = (data.get("token") or "").strip()
        if data.get("generate") or not token:
            token = member_auth.new_token()
        db.set_member_token(name, token, client_role=data.get("client_role") or "member")
        member_auth.reload_cache(db)
        return jsonify({"ok": True, "name": name, "token": token})

    @app.route("/api/collab/member_token", methods=["DELETE"])
    def collab_member_token_del():
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "message": "缺少 name"}), 400
        db.set_member_token(name, "", client_role="lead")
        member_auth.reload_cache(db)
        return jsonify({"ok": True, "name": name})

    # ---------- 组员端引导配置 ----------

    @app.route("/api/collab/member_config", methods=["GET"])
    def collab_member_config():
        """组员端首次配置用：返回主端地址 + 主端密钥。

        仅组长可调用，避免密钥泄露给任意访客。
        """
        role, _name = _identity(_secret(), db)
        if role != "lead":
            return jsonify({"ok": False, "message": "无权限"}), 403
        import socket
        ip = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        web = {}
        try:
            from app import config as _cfg
            web = _cfg.get("web") or {}
        except Exception:
            pass
        return jsonify({
            "ok": True,
            "host": ip,
            "port": web.get("port", 8089),
            "api_secret": _secret() or "",
            "url": "http://%s:%s" % (ip, web.get("port", 8089)),
        })
