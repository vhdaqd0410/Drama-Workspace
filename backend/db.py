# -*- coding: utf-8 -*-
"""Unified SQLite database module for Video Workbench.

Merges schemas & APIs from three legacy apps (nas_bridge, fenji, qa_engine)
into one thread-safe database. All existing callers (sync_engine.py, watcher.py
etc.) keep working unchanged.
"""

import re

import os
import re
import json
import sqlite3
import logging
import threading
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("workbench.db")

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "workbench.db",
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _coerce_priority(value):
    """把待办 priority 规范化为整数，杜绝 int('高') 之类崩溃。

    兼容三种来源：
      - 数值型/数字字符串（新式：priority 即数字，越大越靠前）
      - 中文 '高/中/低'（历史遗留）
      - 英文 'high/medium/low'（任务看板分组）
    无法识别的输入统一回退到 0，保证任何前端传参都不会抛 ValueError。
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower()
    if not text:
        return 0
    if text.isdigit() or (text.lstrip('-').isdigit()):
        try:
            return int(text)
        except (ValueError, OverflowError):
            return 0
    mapping = {"高": 3, "high": 3, "中": 2, "medium": 2, "低": 1, "low": 1}
    return mapping.get(text, 0)


class Database:
    """Per-thread-connection, WAL-enabled SQLite wrapper."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.environ.get("WORKBENCH_DB_PATH") or _DEFAULT_PATH
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        # 并发说明：每线程独立连接(threading.local) + WAL + busy_timeout(5s)，
        # 写操作由 SQLite 文件锁天然串行化，无需 Python 层 _lock（保留它反而误导）。
        self.init_db()

    # ---------- per-thread connection ----------

    def _get_conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def get_conn(self):
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_all(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    # ---------- schema ----------

    def init_db(self):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                production_path TEXT,
                group_path TEXT,
                source_root TEXT,
                department TEXT DEFAULT '',

                sync_status TEXT DEFAULT 'pending',
                sync_progress TEXT DEFAULT '',
                delivery_status TEXT DEFAULT 'pending',
                last_synced_at TEXT,
                last_delivered_at TEXT,
                is_special INTEGER DEFAULT 0,
                special_config TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                custom_status TEXT DEFAULT '',
                total_episodes INTEGER DEFAULT 0,
                current_episodes INTEGER DEFAULT 0,
                episode_plan TEXT DEFAULT '{}'
            )""")
            # 性能索引：覆盖高频查询（月份过滤/状态过滤/部门分组/交付状态/时间排序）
            try:
                c.execute("CREATE INDEX IF NOT EXISTS idx_projects_month ON projects(project_month)")
            except Exception:
                pass
            try:
                c.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(custom_status)")
            except Exception:
                pass
            try:
                c.execute("CREATE INDEX IF NOT EXISTS idx_projects_dept ON projects(department)")
            except Exception:
                pass
            try:
                c.execute("CREATE INDEX IF NOT EXISTS idx_projects_deliv ON projects(delivery_status)")
            except Exception:
                pass
            try:
                c.execute("CREATE INDEX IF NOT EXISTS idx_projects_created ON projects(created_at)")
            except Exception:
                pass

            c.execute("""CREATE TABLE IF NOT EXISTS sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                action TEXT,
                direction TEXT,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT,
                message TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")

            c.execute("""CREATE TABLE IF NOT EXISTS delivery_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                file_name TEXT,
                source_path TEXT,
                dest_path TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT,
                message TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")

            c.execute("""CREATE TABLE IF NOT EXISTS deliver_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                src TEXT,
                dst TEXT,
                total_files INTEGER DEFAULT 0,
                status TEXT,
                message TEXT,
                started_at TEXT,
                finished_at TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")

            c.execute("""CREATE TABLE IF NOT EXISTS qa_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                status TEXT DEFAULT 'running',
                total INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0,
                summary_json TEXT DEFAULT '{}'
            )""")

            c.execute("""CREATE TABLE IF NOT EXISTS qa_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qa_run_id INTEGER NOT NULL,
                video_name TEXT,
                version TEXT,
                status TEXT CHECK (status IN ('pass','warning','fail')),
                details TEXT,
                frame_count INTEGER DEFAULT 0,
                fps REAL DEFAULT 0,
                resolution TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (qa_run_id) REFERENCES qa_runs(id) ON DELETE CASCADE
            )""")

            c.execute("""CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                role TEXT CHECK (role IN ('editor','reviewer','pm')),
                title TEXT DEFAULT '',
                department TEXT DEFAULT '',
                skills TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )""")

            # ---- 融合自「项目档案管理器」：待办事项 + 审计日志 ----
            c.execute("""CREATE TABLE IF NOT EXISTS project_todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                text TEXT NOT NULL,
                done INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_todos_project ON project_todos(project_name)")
            # 任务看板增强：status(待办/进行中/已完成) + remind_at(定时提醒时间)
            try:
                c.execute("ALTER TABLE project_todos ADD COLUMN status TEXT DEFAULT 'todo'")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE project_todos ADD COLUMN remind_at TEXT DEFAULT ''")
            except Exception:
                pass
            # 待办重构：截止日期 + 负责人 + 支持独立待办（project_name 可为空）
            try:
                c.execute("ALTER TABLE project_todos ADD COLUMN due_date TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE project_todos ADD COLUMN assignee TEXT DEFAULT ''")
            except Exception:
                pass
            c.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                action TEXT,
                detail TEXT,
                username TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")

            # ---- 组员协作：阶段打勾（项目 × 人 × 阶段 × 轮次）----
            # phase: cut(剪辑完成) / revise(修改完成) / deliver(交付完成)
            # 一个 (项目,人,阶段,轮次) 只保留一条，重复打勾为 upsert 覆盖。
            c.execute("""CREATE TABLE IF NOT EXISTS project_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                editor TEXT NOT NULL,
                phase TEXT NOT NULL,
                round INTEGER DEFAULT 1,
                done INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                updated_by TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(project_name, editor, phase, round)
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_checks_proj ON project_checks(project_name)")

            # ---- 组员协作：每轮修改的范围（组长选中的要改集数）----
            c.execute("""CREATE TABLE IF NOT EXISTS revision_scope (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                round INTEGER NOT NULL,
                episodes TEXT DEFAULT '[]',
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(project_name, round)
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_revscope_proj ON revision_scope(project_name)")

            # ---- 组员协作：协作通知（组员动作 → 组长可见的待办提示）----
            # kind: check_done(打勾齐) / check_one(单人打勾) / marked(标记已修改)
            c.execute("""CREATE TABLE IF NOT EXISTS collab_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                kind TEXT DEFAULT '',
                phase TEXT DEFAULT '',
                round INTEGER DEFAULT 1,
                actor TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                acked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_collab_acked ON collab_notices(acked)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_logs(project_name)")

            # Migration: add columns if missing
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN title TEXT DEFAULT ''")
            except Exception:
                pass
            # delivered_date：项目交付/归档日期（数据洞察交付日历用）
            try:
                c.execute("ALTER TABLE projects ADD COLUMN delivered_date TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN department TEXT DEFAULT ''")
            except Exception:
                pass
            # 入职/离职时间（YYYY-MM-DD）。离职日期填写后，启动时自动删除该成员。
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN hire_date TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN resign_date TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE projects ADD COLUMN department TEXT DEFAULT ''")
            except Exception:
                pass
            # project_month：项目所属业务月份（YYYY-MM），统计口径关键字段
            try:
                c.execute("ALTER TABLE projects ADD COLUMN project_month TEXT DEFAULT ''")
            except Exception:
                pass
            # editor_workload：独立计数的工作量（{剪辑师: 集数}），不受分集重叠覆盖影响，统计口径来源
            try:
                c.execute("ALTER TABLE projects ADD COLUMN editor_workload TEXT DEFAULT '{}'")
            except Exception:
                pass
            # due_date：项目预计交付/截止日期（YYYY-MM-DD），交付日历延迟预警用
            try:
                c.execute("ALTER TABLE projects ADD COLUMN due_date TEXT DEFAULT ''")
            except Exception:
                pass
            # owner：项目负责人（审核流责任到人）
            try:
                c.execute("ALTER TABLE projects ADD COLUMN owner TEXT DEFAULT ''")
            except Exception:
                pass
            # status_changed_at：最近一次 custom_status 变更时间（超时提醒用）
            try:
                c.execute("ALTER TABLE projects ADD COLUMN status_changed_at TEXT DEFAULT ''")
            except Exception:
                pass
            # 成片存放目录名（覆盖全局 output_dir_name）。空串 = 用全局默认(01上映单集版)。
            # 个别项目的成片不在 01上映单集版，可在成片详情里单独指定存放目录名。
            try:
                c.execute("ALTER TABLE projects ADD COLUMN output_dir_name TEXT DEFAULT ''")
            except Exception:
                pass
            # 交付目录名（覆盖全局 delivery_folder，默认 000交付）。空串 = 用全局默认。
            # 个别项目的交付目录不在全局 000交付，可单独指定。
            try:
                c.execute("ALTER TABLE projects ADD COLUMN delivery_folder TEXT DEFAULT ''")
            except Exception:
                pass
            # 排期看板用：项目开始日期（YYYY-MM-DD），可手动微调；空 = 用 created_at 推算
            try:
                c.execute("ALTER TABLE projects ADD COLUMN start_date TEXT DEFAULT ''")
            except Exception:
                pass
            # 非海外剧标记：1=国内(统计为 AI真人)，0/空=海外(默认 AI海外真人)
            try:
                c.execute("ALTER TABLE projects ADD COLUMN is_domestic INTEGER DEFAULT 0")
            except Exception:
                pass
            # 审核轮次：替代旧的「二/三/四审中」状态。1=首轮，每次「修改中→审核中」+1。
            # 用于修改轮次的打勾隔离：每轮单独记录，避免上一轮勾选残留。
            try:
                c.execute("ALTER TABLE projects ADD COLUMN review_round INTEGER DEFAULT 0")
            except Exception:
                pass
            # 组员端身份令牌（仅 member 账号使用；lead 不需要）
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN token TEXT DEFAULT ''")
            except Exception:
                pass
            # 组员端角色：lead(组长/主端) | member(组员)
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN client_role TEXT DEFAULT 'lead'")
            except Exception:
                pass

    # ---------- migration from legacy DB ----------

    def migrate_from_old(self, old_db_path):
        old_db_path = os.path.abspath(old_db_path)
        if not os.path.isfile(old_db_path):
            logger.warning("Old DB not found: %s", old_db_path)
            return False

        try:
            old_conn = sqlite3.connect(old_db_path)
            old_conn.row_factory = sqlite3.Row
        except Exception as e:
            logger.error("Cannot open old DB: %s", e)
            return False

        try:
            tables = [r[0] for r in old_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]

            mapping = [
                ("projects", ["id", "name", "production_path", "group_path",
                              "source_root", "sync_status", "sync_progress",
                              "delivery_status", "last_synced_at",
                              "last_delivered_at", "is_special",
                              "special_config", "created_at",
                              "custom_status", "total_episodes",
                              "current_episodes", "episode_plan"]),
                ("sync_logs", ["id", "project_name", "action", "direction",
                               "file_path", "file_size", "status", "message",
                               "created_at"]),
                ("delivery_logs", ["id", "project_name", "file_name",
                                   "source_path", "dest_path", "file_size",
                                   "status", "message", "created_at"]),
                ("deliver_runs", ["id", "project_name", "src", "dst",
                                  "total_files", "status", "message",
                                  "started_at", "finished_at",
                                  "created_at"]),
            ]

            counts = {}
            with self.get_conn() as new_conn:
                for table, columns in mapping:
                    if table not in tables:
                        continue
                    rows = [dict(r) for r in old_conn.execute(
                        f"SELECT * FROM {table}"
                    ).fetchall()]
                    migrated = 0
                    for row in rows:
                        values = [row.get(c) for c in columns]
                        placeholders = ",".join(["?"] * len(columns))
                        col_list = ",".join(columns)
                        try:
                            new_conn.execute(
                                f"INSERT OR IGNORE INTO {table} ({col_list}) "
                                f"VALUES ({placeholders})",
                                values,
                            )
                            migrated += 1
                        except Exception as e:
                            logger.debug("Skip row in %s: %s", table, e)
                    counts[table] = migrated
                    logger.info("Migrated %d rows into %s", migrated, table)

            logger.info("Migration complete: %s", counts)
            return True
        finally:
            old_conn.close()

    # ==================== Project CRUD (legacy-compatible) ====================

    @staticmethod
    def extract_department(source_root):
        """从 source_root 路径中提取部门名。
        N:\AI漫剧二部中转              → AI漫剧二部
        N:\AI漫剧一部中转\AI漫剧一部海外 → AI漫剧一部海外
        N:\AI漫剧九部中转\海外          → AI漫剧九部海外
        O:\AI漫剧剪辑一组               → AI漫剧剪辑一组
        """
        if not source_root:
            return ""
        parts = re.split(r'[\\/]', source_root.replace('/', '\\'))
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            return ""
        if len(parts) > 0 and ':' in parts[0]:
            parts = parts[1:]
        suffixes = ('中转',)
        cleaned = []
        for p in parts:
            for s in suffixes:
                if p.endswith(s) and len(p) > len(s):
                    p = p[:-len(s)]
                    break
            if p:
                cleaned.append(p)
        if not cleaned:
            cleaned = parts
        if len(cleaned) >= 2 and cleaned[-1] == "海外":
            return cleaned[-2] + cleaned[-1]
        return cleaned[-1] if cleaned else ""

    def upsert_project(self, name, production_path, group_path,
                       source_root="", is_special=0, special_config=None,
                       department=None):
        sc = json.dumps(special_config or {}, ensure_ascii=False)
        if department is None:
            department = self.extract_department(source_root)
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO projects
                   (name, production_path, group_path, source_root, department,
                    is_special, special_config)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                        production_path=excluded.production_path,
                        group_path=excluded.group_path,
                        source_root=excluded.source_root,
                        department=excluded.department,
                        is_special=excluded.is_special,
                        special_config=excluded.special_config""",
                 (name, production_path, group_path, source_root, department,
                  is_special, sc),
            )


    def get_project(self, name):
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE name=?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_projects(self):
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def list_projects(self):
        return self.get_all_projects()

    def delete_project(self, name):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM projects WHERE name=?", (name,))

    def update_project_status(self, name, **kwargs):
        if not kwargs:
            return
        # 交付联动：一旦置为已交付(delivered)，若尚无 delivered_date 则自动补记交付日期
        # （取 last_delivered_at 的日期，否则当天），保证交付日历自动更新
        if kwargs.get("delivery_status") == "delivered":
            proj = self.get_project(name)
            if proj and not (proj.get("delivered_date") or "").strip():
                src = kwargs.get("last_delivered_at") or proj.get("last_delivered_at") or ""
                dd = (src or "")[:10]
                if not dd:
                    from datetime import datetime as _dt
                    dd = _dt.now().strftime("%Y-%m-%d")
                kwargs["delivered_date"] = dd
        # 审核流：custom_status 变化时记录变更时间（超时提醒用）；除非显式传入 status_changed_at
        if kwargs.get("custom_status") is not None and "status_changed_at" not in kwargs:
            from datetime import datetime as _dt2
            kwargs["status_changed_at"] = _dt2.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [name]
        with self.get_conn() as conn:
            conn.execute(
                f"UPDATE projects SET {fields} WHERE name=?", values
            )

    def set_episodes(self, name, total, current):
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE projects SET total_episodes=?, current_episodes=? "
                "WHERE name=?",
                (int(total), int(current), name),
            )

    def set_episode_plan(self, name, plan_dict):
        if not isinstance(plan_dict, dict):
            plan_dict = {}
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE projects SET episode_plan=? WHERE name=?",
                (json.dumps(plan_dict, ensure_ascii=False), name),
            )

    def set_output_dir_name(self, name, dir_name):
        """设置项目单独的成片存放目录名（空串 = 使用全局默认）。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE projects SET output_dir_name=? WHERE name=?",
                (str(dir_name or "").strip(), name),
            )

    def set_delivery_folder(self, name, folder_name):
        """设置项目单独的交付目录名（空串 = 使用全局默认）。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE projects SET delivery_folder=? WHERE name=?",
                (str(folder_name or "").strip(), name),
            )

    def get_episode_plan(self, name):
        p = self.get_project(name)
        if not p:
            return {}
        raw = p.get("episode_plan") or "{}"
        try:
            v = json.loads(raw) if isinstance(raw, str) else raw
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}

    def set_editor_workload(self, name, workload_dict):
        """写入项目独立计数的工作量 {剪辑师: 集数}（统计口径来源）。"""
        if not isinstance(workload_dict, dict):
            workload_dict = {}
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE projects SET editor_workload=? WHERE name=?",
                (json.dumps(workload_dict, ensure_ascii=False), name),
            )

    def get_editor_workload(self, name):
        p = self.get_project(name)
        if not p:
            return {}
        raw = p.get("editor_workload") or "{}"
        try:
            v = json.loads(raw) if isinstance(raw, str) else raw
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}

    # ==================== Sync logs ====================

    def add_sync_log(self, project_name, action, direction="", file_path="",
                     file_size=0, status="info", message=""):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO sync_logs
                   (project_name, action, direction, file_path, file_size,
                    status, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_name, action, direction, file_path,
                 file_size, status, message),
            )

    def get_sync_logs(self, project_name=None, limit=50):
        with self.get_conn() as conn:
            if project_name:
                rows = conn.execute(
                    "SELECT * FROM sync_logs WHERE project_name=? "
                    "ORDER BY id DESC LIMIT ?",
                    (project_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ==================== Delivery logs ====================

    def add_delivery_log(self, project_name, file_name, source_path="",
                         dest_path="", file_size=0, status="info", message=""):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO delivery_logs
                   (project_name, file_name, source_path, dest_path,
                    file_size, status, message)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_name, file_name, source_path, dest_path,
                 file_size, status, message),
            )

    def get_delivery_logs(self, project_name=None, limit=50):
        with self.get_conn() as conn:
            if project_name:
                rows = conn.execute(
                    "SELECT * FROM delivery_logs WHERE project_name=? "
                    "ORDER BY id DESC LIMIT ?",
                    (project_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM delivery_logs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_recent_logs(self, limit=100):
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT 'sync' AS type, project_name, action AS title,
                          status, message, created_at
                   FROM sync_logs
                   UNION ALL
                   SELECT 'delivery' AS type, project_name, file_name AS title,
                          status, message, created_at
                   FROM delivery_logs
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ==================== Deliver runs ====================

    def insert_deliver_run(self, project_name, src="", dst="",
                           total_files=0, status="running", message="",
                           started_at=""):
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO deliver_runs
                   (project_name, src, dst, total_files, status, message,
                    started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project_name, src, dst, total_files,
                 status, message, started_at),
            )
            return cur.lastrowid

    def finish_deliver_run(self, run_id, status, message="", finished_at=""):
        with self.get_conn() as conn:
            conn.execute(
                """UPDATE deliver_runs SET status=?, message=?, finished_at=?
                   WHERE id=?""",
                (status, message, finished_at, run_id),
            )

    def get_deliver_runs(self, project_name=None, limit=30):
        with self.get_conn() as conn:
            if project_name:
                rows = conn.execute(
                    "SELECT * FROM deliver_runs WHERE project_name=? "
                    "ORDER BY id DESC LIMIT ?",
                    (project_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM deliver_runs ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    # ==================== QA runs (NEW) ====================

    def create_qa_run(self, project_name, started_at=None, status="running"):
        if started_at is None:
            started_at = _now()
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO qa_runs (project_name, started_at, status)
                   VALUES (?, ?, ?)""",
                (project_name, started_at, status),
            )
            return cur.lastrowid

    def update_qa_run(self, run_id, **kwargs):
        if not kwargs:
            return
        fields = []
        values = []
        for k, v in kwargs.items():
            if k == "summary_json" and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            fields.append(f"{k}=?")
            values.append(v)
        values.append(run_id)
        with self.get_conn() as conn:
            conn.execute(
                f"UPDATE qa_runs SET {', '.join(fields)} WHERE id=?", values
            )

    def get_qa_run(self, run_id):
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM qa_runs WHERE id=?", (run_id,)
            ).fetchone()
            d = dict(row) if row else None
            if d and isinstance(d.get("summary_json"), str):
                try:
                    d["summary_json"] = json.loads(d["summary_json"])
                except Exception:
                    pass
            return d

    def list_qa_runs_for_project(self, project_name, limit=50):
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_runs WHERE project_name=? "
                "ORDER BY id DESC LIMIT ?",
                (project_name, limit),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("summary_json"), str):
                    try:
                        d["summary_json"] = json.loads(d["summary_json"])
                    except Exception:
                        pass
                out.append(d)
            return out

    def list_all_qa_runs(self, limit=100):
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("summary_json"), str):
                    try:
                        d["summary_json"] = json.loads(d["summary_json"])
                    except Exception:
                        pass
                out.append(d)
            return out

    def insert_qa_result(self, qa_run_id, video_name, version, status,
                         details="", frame_count=0, fps=0, resolution=""):
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO qa_results
                   (qa_run_id, video_name, version, status, details,
                    frame_count, fps, resolution)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (qa_run_id, video_name, version, status, details,
                 frame_count, fps, resolution),
            )

    def get_qa_results(self, qa_run_id):
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_results WHERE qa_run_id=? ORDER BY id",
                (qa_run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_qa_run(self, run_id):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM qa_results WHERE qa_run_id=?", (run_id,))
            conn.execute("DELETE FROM qa_runs WHERE id=?", (run_id,))

    # ==================== Team members (NEW) ====================

    def add_member(self, name, role="editor", title="", department="", skills=None):
        if role not in ("editor", "reviewer", "pm"):
            role = "editor"
        sk = json.dumps(skills or [], ensure_ascii=False)
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO team_members (name, role, title, department, skills)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       role=excluded.role,
                       title=COALESCE(excluded.title, team_members.title),
                       department=COALESCE(excluded.department, team_members.department),
                       skills=excluded.skills""",
                (name, role, title or "", department or "", sk),
            )

    def list_members(self, role=None):
        with self.get_conn() as conn:
            if role:
                rows = conn.execute(
                    "SELECT * FROM team_members WHERE role=? ORDER BY name",
                    (role,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM team_members ORDER BY role, name"
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("skills"), str):
                    try:
                        d["skills"] = json.loads(d["skills"])
                    except Exception:
                        d["skills"] = []
                out.append(d)
            return out

    def delete_member(self, name):
        with self.get_conn() as conn:
            conn.execute(
                "DELETE FROM team_members WHERE name=?", (name,)
            )

    def purge_resigned_members(self):
        """删除已填写离职日期且离职时间已到（<= 当前月份）的成员。

        离职日期格式 YYYY-MM 或 YYYY-MM-DD；仅当 resign_date 非空且不晚于当前月
        才删除（次月自动删除的语义：填了上个月或更早的离职日期即删除）。
        返回被删除的成员姓名列表。
        """
        from datetime import datetime as _dt
        now = _dt.now()
        cur_ym = now.strftime("%Y-%m")
        removed = []
        try:
            with self.get_conn() as conn:
                rows = conn.execute(
                    "SELECT name, resign_date FROM team_members "
                    "WHERE resign_date IS NOT NULL AND resign_date != ''"
                ).fetchall()
            for name, rd in rows:
                rd = (rd or "").strip()
                if not rd:
                    continue
                # 统一取 YYYY-MM 前缀比较
                ym = rd[:7]
                if ym and ym <= cur_ym:
                    with self.get_conn() as conn:
                        conn.execute("DELETE FROM team_members WHERE name=?", (name,))
                    removed.append(name)
        except Exception:
            pass
        return removed

    def update_member(self, name, **kwargs):
        if not kwargs:
            return
        if "role" in kwargs and kwargs["role"] not in ("editor", "reviewer", "pm"):
            raise ValueError(f"Invalid role: {kwargs['role']}")
        if "skills" in kwargs and isinstance(kwargs["skills"], (list, dict)):
            kwargs["skills"] = json.dumps(kwargs["skills"], ensure_ascii=False)
        fields = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [name]
        with self.get_conn() as conn:
            conn.execute(
                f"UPDATE team_members SET {fields} WHERE name=?", values
            )

    # ==================== 用户设置（持久化到后端） ====================

    def get_setting(self, key, default=""):
        """读取用户设置（key-value）。"""
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key=?", (key,)
                ).fetchone()
                return row[0] if row else default
        except Exception:
            return default

    def set_setting(self, key, value):
        """写入用户设置（key-value），不存在则插入。"""
        if value is None:
            value = ""
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        try:
            with self.get_conn() as conn:
                conn.execute(
                    """INSERT INTO app_settings(key, value) VALUES(?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                    (key, str(value)),
                )
        except Exception:
            pass

    def get_all_settings(self):
        """返回全部用户设置 dict。"""
        try:
            with self.get_conn() as conn:
                rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
                return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    # ==================== 忽略/软删除项目（扫描时跳过） ====================

    def get_ignored_projects(self):
        """返回被忽略（软删除）的项目名列表。"""
        raw = self.get_setting("ignored_projects", "[]")
        try:
            data = json.loads(raw) if raw else []
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def add_ignored_project(self, name):
        """把项目加入忽略列表（扫描时跳过）。"""
        ignored = self.get_ignored_projects()
        if name not in ignored:
            ignored.append(name)
            self.set_setting("ignored_projects", ignored)

    def remove_ignored_project(self, name):
        """从忽略列表移除（恢复项目）。"""
        ignored = [n for n in self.get_ignored_projects() if n != name]
        self.set_setting("ignored_projects", ignored)

    # ==================== 项目待办事项 ====================
    def get_project_todos(self, project_name):
        try:
            with self.get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM project_todos WHERE project_name=? ORDER BY done ASC, priority DESC, id DESC",
                    (project_name,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def get_all_todos(self, include_done=False, keyword=""):
        """跨项目查询所有待办（全局待办视图用）。按未完成优先、项目分组排序。
        project_name 为空表示独立待办。"""
        try:
            with self.get_conn() as conn:
                sql = ("SELECT t.*, p.custom_status AS status "
                       "FROM project_todos t LEFT JOIN projects p ON p.name=t.project_name ")
                conds = []
                args = []
                if not include_done:
                    conds.append("t.done=0")
                if keyword:
                    conds.append("(t.project_name LIKE ? OR t.text LIKE ?)")
                    kw = "%" + keyword + "%"
                    args += [kw, kw]
                if conds:
                    sql += " WHERE " + " AND ".join(conds)
                sql += " ORDER BY t.done ASC, t.priority DESC, t.project_name, t.id DESC"
                rows = conn.execute(sql, args).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def add_project_todo(self, project_name, text, priority=0, status='todo', remind_at='', due_date='', assignee=''):
        with self.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO project_todos(project_name, text, priority, status, remind_at, due_date, assignee) VALUES(?,?,?,?,?,?,?)",
                (project_name, text, _coerce_priority(priority), str(status), str(remind_at or ''),
                 str(due_date or ''), str(assignee or '')))
            return cur.lastrowid

    def update_project_todo(self, todo_id, done=None, text=None, priority=None, status=None, remind_at=None, due_date=None, assignee=None):
        with self.get_conn() as conn:
            if done is not None:
                conn.execute("UPDATE project_todos SET done=? WHERE id=?",
                             (1 if done else 0, todo_id))
            if text is not None:
                conn.execute("UPDATE project_todos SET text=? WHERE id=?",
                             (str(text).strip(), todo_id))
            if priority is not None:
                conn.execute("UPDATE project_todos SET priority=? WHERE id=?",
                             (_coerce_priority(priority), todo_id))
            if status is not None:
                conn.execute("UPDATE project_todos SET status=? WHERE id=?",
                             (str(status), todo_id))
            if remind_at is not None:
                conn.execute("UPDATE project_todos SET remind_at=? WHERE id=?",
                             (str(remind_at).strip(), todo_id))
            if due_date is not None:
                conn.execute("UPDATE project_todos SET due_date=? WHERE id=?",
                             (str(due_date).strip(), todo_id))
            if assignee is not None:
                conn.execute("UPDATE project_todos SET assignee=? WHERE id=?",
                             (str(assignee).strip(), todo_id))

    def delete_project_todo(self, todo_id):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM project_todos WHERE id=?", (todo_id,))

    # ==================== 组员协作：阶段打勾 ====================

    def get_project_checks(self, project_name, phase=None, round_no=None):
        """读取某项目的打勾记录。可按阶段/轮次过滤。"""
        try:
            with self.get_conn() as conn:
                sql = "SELECT * FROM project_checks WHERE project_name=?"
                args = [project_name]
                if phase:
                    sql += " AND phase=?"
                    args.append(phase)
                if round_no is not None:
                    sql += " AND round=?"
                    args.append(int(round_no))
                sql += " ORDER BY phase, editor"
                return [dict(r) for r in conn.execute(sql, args).fetchall()]
        except Exception:
            logger.warning("读取打勾记录失败", exc_info=True)
            return []

    def set_project_check(self, project_name, editor, phase, round_no=1,
                          done=1, note='', updated_by=''):
        """写入/更新一条打勾记录（upsert，同 (项目,人,阶段,轮次) 唯一）。"""
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO project_checks
                     (project_name, editor, phase, round, done, note, updated_by, updated_at)
                   VALUES (?,?,?,?,?,?,?, datetime('now','localtime'))
                   ON CONFLICT(project_name, editor, phase, round) DO UPDATE SET
                     done=excluded.done,
                     note=excluded.note,
                     updated_by=excluded.updated_by,
                     updated_at=datetime('now','localtime')""",
                (project_name, str(editor), str(phase), int(round_no),
                 1 if done else 0, str(note or ''), str(updated_by or '')))
        return True

    def count_checks(self, project_name, phase, round_no=None, done_only=True):
        """统计某项目某阶段的打勾数量。"""
        try:
            with self.get_conn() as conn:
                sql = ("SELECT COUNT(*) FROM project_checks "
                       "WHERE project_name=? AND phase=?")
                args = [project_name, phase]
                if done_only:
                    sql += " AND done=1"
                if round_no is not None:
                    sql += " AND round=?"
                    args.append(int(round_no))
                return int(conn.execute(sql, args).fetchone()[0])
        except Exception:
            return 0

    def clear_checks(self, project_name, phase, round_no=None):
        """清除打勾记录（用于轮次推进时重打）。"""
        with self.get_conn() as conn:
            if round_no is None:
                conn.execute(
                    "DELETE FROM project_checks WHERE project_name=? AND phase=?",
                    (project_name, phase))
            else:
                conn.execute(
                    "DELETE FROM project_checks WHERE project_name=? AND phase=? AND round=?",
                    (project_name, phase, int(round_no)))

    # ==================== 组员协作：修改范围 ====================

    def set_revision_scope(self, project_name, round_no, episodes, note=''):
        """记录某轮修改选中的集数（episodes 为列表）。"""
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO revision_scope(project_name, round, episodes, note)
                   VALUES (?,?,?,?)
                   ON CONFLICT(project_name, round) DO UPDATE SET
                     episodes=excluded.episodes, note=excluded.note""",
                (project_name, int(round_no),
                 json.dumps(list(episodes or []), ensure_ascii=False), str(note or '')))
        return True

    def get_revision_scope(self, project_name, round_no):
        """读取某轮修改选中的集数，返回 (episodes_list, note)。"""
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    "SELECT episodes, note FROM revision_scope "
                    "WHERE project_name=? AND round=?",
                    (project_name, int(round_no))).fetchone()
            if not row:
                return [], ''
            eps = row[0] or '[]'
            try:
                eps = json.loads(eps)
            except Exception:
                eps = []
            return list(eps), (row[1] or '')
        except Exception:
            return [], ''

    # ==================== 组员协作：协作通知 ====================

    def add_collab_notice(self, project_name, kind, phase='', round_no=1,
                          actor='', detail=''):
        with self.get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO collab_notices
                     (project_name, kind, phase, round, actor, detail)
                   VALUES (?,?,?,?,?,?)""",
                (project_name, str(kind), str(phase), int(round_no),
                 str(actor or ''), str(detail or '')))
            return cur.lastrowid

    def list_collab_notices(self, include_acked=False, limit=100):
        try:
            with self.get_conn() as conn:
                sql = "SELECT * FROM collab_notices"
                if not include_acked:
                    sql += " WHERE acked=0"
                sql += " ORDER BY id DESC LIMIT ?"
                return [dict(r) for r in conn.execute(sql, (int(limit),)).fetchall()]
        except Exception:
            return []

    def ack_collab_notice(self, notice_id=None, project_name=None, kind=None):
        """标记协作通知已处理。可传 id，或按项目+类型批处理。"""
        with self.get_conn() as conn:
            if notice_id is not None:
                conn.execute("UPDATE collab_notices SET acked=1 WHERE id=?",
                             (int(notice_id),))
                return
            sql = "UPDATE collab_notices SET acked=1 WHERE acked=0"
            args = []
            if project_name:
                sql += " AND project_name=?"
                args.append(project_name)
            if kind:
                sql += " AND kind=?"
                args.append(kind)
            conn.execute(sql, args)

    def count_unacked_notices(self):
        try:
            with self.get_conn() as conn:
                return int(conn.execute(
                    "SELECT COUNT(*) FROM collab_notices WHERE acked=0").fetchone()[0])
        except Exception:
            return 0

    # ==================== 组员协作：身份令牌 ====================

    def get_member_by_token(self, token):
        """按令牌查组员（组员端鉴权用）。"""
        t = str(token or '').strip()
        if not t:
            return None
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM team_members WHERE token=? AND token<>''",
                    (t,)).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def list_members_ext(self):
        """列出成员（含 token / client_role，供设置页管理）。"""
        try:
            with self.get_conn() as conn:
                return [dict(r) for r in conn.execute(
                    "SELECT * FROM team_members ORDER BY client_role, name").fetchall()]
        except Exception:
            return []

    def set_member_token(self, name, token, client_role=None):
        """设置成员的组员端令牌（及角色）。"""
        with self.get_conn() as conn:
            conn.execute("UPDATE team_members SET token=? WHERE name=?",
                         (str(token or ''), name))
            if client_role:
                conn.execute("UPDATE team_members SET client_role=? WHERE name=?",
                             (str(client_role), name))

    # ==================== 审计日志 ====================
    def add_audit_log(self, project_name, action, detail="", username=""):
        try:
            with self.get_conn() as conn:
                conn.execute(
                    "INSERT INTO audit_logs(project_name, action, detail, username) VALUES(?,?,?,?)",
                    (project_name, action, detail, username))
        except Exception:
            pass

    def get_audit_logs(self, project_name=None, limit=100):
        try:
            with self.get_conn() as conn:
                if project_name:
                    rows = conn.execute(
                        "SELECT * FROM audit_logs WHERE project_name=? ORDER BY created_at DESC, id DESC LIMIT ?",
                        (project_name, limit)).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT ?",
                        (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def prune_logs(self, keep_days=90):
        """清理超过 keep_days 的日志表记录，防止 DB 无限膨胀。
        返回被清理的总行数。表：
          - delivery_logs（交付记录，量大）
          - sync_logs（同步日志）
          - audit_logs（审计日志）
        deliver_runs / qa_runs 保留（可能有进行中任务），不做清理。
        """
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d %H:%M:%S")
        total = 0
        tables = ["delivery_logs", "sync_logs", "audit_logs"]
        try:
            with self.get_conn() as conn:
                for t in tables:
                    try:
                        cur = conn.execute(
                            "DELETE FROM %s WHERE created_at < ?" % t, (cutoff,))
                        total += cur.rowcount
                    except Exception:
                        pass
            return total
        except Exception:
            return 0


db = Database()


def init_db(db_path):
    global db
    db = Database(db_path)
    return db
