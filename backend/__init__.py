# -*- coding: utf-8 -*-
from .config import load_config, save_config, get, DB_PATH
from .db import db, Database, init_db
from .qa_engine import qa_engine, QAEngine
# sync_engine 延迟导入

def init_workbench(db_path=None):
    load_config()
    if db_path is None:
        from pathlib import Path
        db_path = str(DB_PATH)
    init_db(db_path)
    return db
