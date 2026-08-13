# -*- coding: utf-8 -*-
"""统一配置管理。"""
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger("config")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "workbench.db"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CONFIG = {
    "server": {"host": "127.0.0.1", "port": 8089, "debug": False},
    "nas": {
        "group_root": r"O:\AI漫剧剪辑一组",
        "production_roots": [r"O:\AI漫剧剪辑一组"],
        "source_roots": [],
        "nas_prefixes": ["O:\\"],
        "exclude_keywords": ["已交付", "已完成", "备份", "bak", ".old", "._"],
        "include_exts": [".mp4", ".mov", ".mkv", ".srt", ".ass", ".json", ".xml", ".txt", ".psd"],
    },
    "qa": {"workers": 4, "ffmpeg_path": "", "ffprobe_path": ""},
    "fenji": {
        "default_total_episodes": 80,
        "suggested_names": ["张大强", "李小明", "王大锤", "赵四", "钱多多", "孙小美"],
    },
    "paths": {
        "ffmpeg": "",
        "ffprobe": "",
        "old_nas_bridge_db": r"C:\Users\Admin\Desktop\钉钉机器人\nas-bridge\nas_bridge.db",
    },
}

_config = None


def load_config():
    global _config
    if _config is not None:
        return _config
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            _config = _deep_merge(DEFAULT_CONFIG, user_cfg)
        except Exception as e:
            logger.warning("配置文件损坏，使用默认值: %s", e)
            _config = json.loads(json.dumps(DEFAULT_CONFIG))
    else:
        _config = json.loads(json.dumps(DEFAULT_CONFIG))
        save_config(_config)
    _resolve_ffmpeg()
    return _config


def save_config(cfg=None):
    global _config
    if cfg is not None:
        _config = cfg
    if _config is None:
        _config = json.loads(json.dumps(DEFAULT_CONFIG))
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(_config, f, ensure_ascii=False, indent=2)


def get(key_path, default=None):
    cfg = load_config()
    cur = cfg
    for part in key_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def _deep_merge(base, override):
    out = json.loads(json.dumps(base))
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_ffmpeg():
    try:
        import shutil
        for bin_name, cfg_key in [("ffmpeg", "ffmpeg_path"), ("ffprobe", "ffprobe_path")]:
            path = get(f"qa.{cfg_key}", "") or shutil.which(bin_name)
            if not path:
                dist_dir = Path(r"C:\Users\Admin\Desktop\视频检查工具\视频质检工具\dist\视频质检工具")
                candidate = dist_dir / f"{bin_name}.exe"
                if candidate.exists():
                    path = str(candidate)
            if path:
                _config.setdefault("qa", {})[cfg_key] = path
                os.environ.setdefault(bin_name.upper() + "_PATH", path)
    except Exception:
        pass
