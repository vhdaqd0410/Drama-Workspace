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


class Database:
    """Per-thread-connection, WAL-enabled SQLite wrapper."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.environ.get("WORKBENCH_DB_PATH") or _DEFAULT_PATH
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
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
            c.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                action TEXT,
                detail TEXT,
                username TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_logs(project_name)")

            # Migration: add columns if missing
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN title TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE team_members ADD COLUMN department TEXT DEFAULT ''")
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE projects ADD COLUMN department TEXT DEFAULT ''")
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

    def add_project_todo(self, project_name, text, priority=0):
        with self.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO project_todos(project_name, text, priority) VALUES(?,?,?)",
                (project_name, text, int(priority or 0)))
            return cur.lastrowid

    def update_project_todo(self, todo_id, done=None, text=None, priority=None):
        with self.get_conn() as conn:
            if done is not None:
                conn.execute("UPDATE project_todos SET done=? WHERE id=?",
                             (1 if done else 0, todo_id))
            if text is not None:
                conn.execute("UPDATE project_todos SET text=? WHERE id=?",
                             (str(text).strip(), todo_id))
            if priority is not None:
                conn.execute("UPDATE project_todos SET priority=? WHERE id=?",
                             (int(priority or 0), todo_id))

    def delete_project_todo(self, todo_id):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM project_todos WHERE id=?", (todo_id,))

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


db = Database()


def init_db(db_path):
    global db
    db = Database(db_path)
    return db
