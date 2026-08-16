# -*- coding: utf-8 -*-
"""AI后期剪辑提成工具 — 配置加载与校验模块

替代原来 generate_commission.py 中散落的 load_config() 和模块级全局变量。
提供：
- 类型安全的配置加载（JSON -> AppConfig）
- Schema 校验（快速失败，明确错误）
- 原子写入（先写临时文件再 rename，避免崩溃损坏配置）
"""
from __future__ import annotations

import json
import os
import tempfile
import hashlib
from typing import Optional

import constants as C
from models import AppConfig, QuotaRule, GroupInfo


# ===================== 加载 =====================

def load_config(config_path: str) -> AppConfig:
    """加载 config.json 并解析为 AppConfig。

    如果文件不存在或解析失败则抛出明确异常，不再静默 fallback。
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件不存在: {config_path}\n"
            f"请参考 config.example.json 创建 config.json"
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"配置文件 {config_path} JSON 格式错误:\n"
            f"  行 {e.lineno}, 列 {e.colno}: {e.msg}\n"
            f"请用 JSON 校验工具检查格式。"
        ) from e

    if not isinstance(raw, dict):
        raise ValueError(f"配置文件根元素必须是 JSON 对象 (dict)，当前为 {type(raw).__name__}")

    # --- 校验并构建 ---
    return _parse_config_dict(raw, config_path)


def reload_config(config_path: str) -> AppConfig:
    """重新加载配置（GUI 修改后使用）。"""
    return load_config(config_path)


# ===================== 内部解析 =====================

def _parse_config_dict(raw: dict, source_label: str = "") -> AppConfig:
    """从原始 dict 解析 AppConfig，附带详细的校验错误信息。"""
    errors: list[str] = []
    label = f" ({source_label})" if source_label else ""

    # --- 解析 rules ---
    raw_rules = raw.get("rules", {})
    if not isinstance(raw_rules, dict):
        errors.append(f"  rules: 应为对象(dict)，当前为 {type(raw_rules).__name__}")
        raw_rules = {}

    rules: dict[str, QuotaRule] = {}
    known_roles = [C.ROLE_CARD1, C.ROLE_CARD2, C.ROLE_ASSISTANT, C.ROLE_LEADER]
    for role in known_roles:
        rd = raw_rules.get(role, {})
        if rd and not isinstance(rd, dict):
            errors.append(f"  rules.{role}: 应为对象(dict)，当前为 {type(rd).__name__}")
            rd = {}
        rules[role] = QuotaRule.from_config(role, rd)

    # 检查是否缺少关键角色规则
    for role in [C.ROLE_CARD1, C.ROLE_CARD2, C.ROLE_LEADER]:
        if role != C.ROLE_LEADER and rules[role].quota <= 0:
            errors.append(f"  rules.{role}.基准集数: 不能为 0 或负数，当前为 {rules[role].quota}")
        if role != C.ROLE_LEADER and rules[role].over_price < 0:
            errors.append(f"  rules.{role}.超额每集: 不能为负数，当前为 {rules[role].over_price}")
        if role != C.ROLE_LEADER and rules[role].short_penalty < 0:
            errors.append(f"  rules.{role}.缺集每集扣: 不能为负数，当前为 {rules[role].short_penalty}")
        if role == C.ROLE_LEADER and rules[role].eps_price <= 0:
            errors.append(f"  rules.{role}.每集单价: 不能为 0 或负数，当前为 {rules[role].eps_price}")
        if role == C.ROLE_LEADER and rules[role].project_bonus < 0:
            errors.append(f"  rules.{role}.组内每部提成: 不能为负数，当前为 {rules[role].project_bonus}")

    # --- 解析 人员角色 ---
    raw_person_roles = raw.get("人员角色", {})
    if not isinstance(raw_person_roles, dict):
        errors.append(f"  人员角色: 应为对象(dict)，当前为 {type(raw_person_roles).__name__}")
        raw_person_roles = {}

    person_roles: dict[str, str] = {}
    for name, role_str in raw_person_roles.items():
        if not isinstance(role_str, str):
            errors.append(f"  人员角色.{name}: 角色名应为字符串")
            continue
        normalized = _validate_role(role_str)
        if normalized is None:
            errors.append(f"  人员角色.{name}: 未知角色 '{role_str}'，有效值: {known_roles}")
            continue
        person_roles[name] = normalized

    # --- 解析 小组 ---
    raw_groups = raw.get("小组", {})
    if not isinstance(raw_groups, dict):
        errors.append(f"  小组: 应为对象(dict)，当前为 {type(raw_groups).__name__}")
        raw_groups = {}

    groups: dict[str, GroupInfo] = {}
    for gname, gdata in raw_groups.items():
        if not isinstance(gdata, dict):
            errors.append(f"  小组.{gname}: 应为对象(dict)")
            continue
        leader = gdata.get("组长", "")
        members = gdata.get("成员", [])
        if not isinstance(members, list):
            errors.append(f"  小组.{gname}.成员: 应为数组(list)")
            members = []
        # 检查组长和成员是否在人员名单中
        if leader and leader not in person_roles:
            errors.append(f"  小组.{gname}.组长 '{leader}': 不在人员角色名单中")
        for member in members:
            if member not in person_roles:
                errors.append(f"  小组.{gname}.成员 '{member}': 不在人员角色名单中")
        groups[gname] = GroupInfo(leader=leader, members=members)

    # --- 解析 人员排序 ---
    raw_order = raw.get("人员排序", [])
    if not isinstance(raw_order, list):
        errors.append(f"  人员排序: 应为数组(list)，当前为 {type(raw_order).__name__}")
        raw_order = []

    person_order: list[str] = []
    seen_names = set()
    for name in raw_order:
        if name in person_roles and name not in seen_names:
            person_order.append(name)
            seen_names.add(name)

    # 补上没有在排序中的已配置人员
    for name in person_roles:
        if name not in seen_names:
            person_order.append(name)
            seen_names.add(name)

    # --- 解析 选人模版 ---
    raw_templates = raw.get("personnel_templates", {})
    if not isinstance(raw_templates, dict):
        errors.append(f"  personnel_templates: 应为对象(dict)，当前为 {type(raw_templates).__name__}")
        raw_templates = {}

    personnel_templates: dict[str, list[str]] = {}
    for tname, tlist in raw_templates.items():
        if not isinstance(tlist, list):
            errors.append(f"  personnel_templates.{tname}: 应为数组(list)，当前为 {type(tlist).__name__}")
            continue
        personnel_templates[str(tname)] = [str(n) for n in tlist]

    # --- 解析 GUI 使用设置 ---
    raw_app_settings = raw.get("app_settings", {})
    if not isinstance(raw_app_settings, dict):
        errors.append(f"  app_settings: 应为对象(dict)，当前为 {type(raw_app_settings).__name__}")
        raw_app_settings = {}

    # --- 解析主题、月度目标、项目模板、版本等扩展字段 ---
    theme = raw.get("theme", "light")
    if theme not in ("light", "dark"):
        theme = "light"
    raw_monthly_goals = raw.get("monthly_goals", {})
    if not isinstance(raw_monthly_goals, dict):
        raw_monthly_goals = {}
    raw_project_templates = raw.get("project_templates", {})
    if not isinstance(raw_project_templates, dict):
        raw_project_templates = {}
    version = str(raw.get("version", "1.0.0"))
    update_check = bool(raw.get("update_check", True))
    raw_favorites = raw.get("favorites", [])
    if not isinstance(raw_favorites, list):
        raw_favorites = []
    favorites = [str(x) for x in raw_favorites]

    # --- 汇总错误 ---
    if errors:
        error_msg = f"配置校验失败{label}:\n" + "\n".join(errors)
        raise ValueError(error_msg)

    return AppConfig(
        person_roles=person_roles,
        rules=rules,
        groups=groups,
        person_order=person_order,
        personnel_templates=personnel_templates,
        app_settings=dict(raw_app_settings),
        theme=theme,
        monthly_goals=dict(raw_monthly_goals),
        project_templates=dict(raw_project_templates),
        version=version,
        update_check=update_check,
        favorites=favorites,
    )


def _validate_role(role_str: str) -> Optional[str]:
    """校验角色字符串是否合法，返回标准化名称。"""
    role = role_str.strip()
    aliases = {
        C.ROLE_CARD1: C.ROLE_CARD1,
        C.ROLE_CARD2: C.ROLE_CARD2,
        C.ROLE_ASSISTANT: C.ROLE_ASSISTANT,
        C.ROLE_LEADER: C.ROLE_LEADER,
        C.ROLE_SUB_LEADER: C.ROLE_SUB_LEADER,
    }
    return aliases.get(role)


# ===================== 保存 =====================

def save_config(app_config: AppConfig, config_path: str) -> str:
    """原子保存配置（先写临时文件，成功后再 rename）。

    Returns:
        config_path（用于链式调用）
    """
    data = app_config.to_dict()
    data.setdefault("_comment", "角色及提成配置 - 修改此文件后重新运行工具即可生效")

    json_text = json.dumps(data, ensure_ascii=False, indent=2)

    dir_path = os.path.dirname(config_path)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        dir=dir_path,
        delete=False,
    ) as tmp:
        tmp.write(json_text)
        tmp_path = tmp.name

    try:
        os.replace(tmp_path, config_path)
    except Exception:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return config_path


def load_config_or_default(config_path: str) -> AppConfig:
    """尝试加载配置，失败时返回合理的空 AppConfig（不崩溃）。"""
    try:
        return load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        import sys
        print(f"⚠️ 配置加载失败: {e}", file=sys.stderr)
        print("⚠️ 使用空配置继续运行。请在 GUI 中通过「角色配置」设置。", file=sys.stderr)
        return AppConfig()


# ===================== 多环境配置 =====================

def get_env_dir(config_path):
    """返回环境配置目录（与 config.json 同级的 environments/）"""
    base = os.path.dirname(os.path.abspath(config_path))
    return os.path.join(base, 'environments')


def list_environments(config_path):
    """列出所有可用环境名。返回 ["默认"] + 已保存的环境名。"""
    env_dir = get_env_dir(config_path)
    names = []
    if os.path.isdir(env_dir):
        for fn in sorted(os.listdir(env_dir)):
            if fn.endswith('.json'):
                names.append(fn[:-5])
    return ['默认'] + names


def load_environment(config_path, name):
    """加载指定环境的配置。'默认' 表示 config.json 本身。"""
    if name in (None, '', '默认'):
        return load_config(config_path)
    env_path = os.path.join(get_env_dir(config_path), f'{name}.json')
    if not os.path.exists(env_path):
        raise FileNotFoundError(f'环境配置不存在: {env_path}')
    return load_config(env_path)


def save_environment(config_path, name, app_config):
    """保存当前配置为指定环境。'默认' 表示 config.json 本身。"""
    if name in (None, '', '默认'):
        return save_config(app_config, config_path)
    env_dir = get_env_dir(config_path)
    os.makedirs(env_dir, exist_ok=True)
    env_path = os.path.join(env_dir, f'{name}.json')
    return save_config(app_config, env_path)


# ===================== 数据加密（K） =====================

def encrypt_data(text, password):
    """用密码对文本做简单可逆加密（XOR + base64）。

    Args:
        text: 明文
        password: 密码

    Returns:
        str: 密文（base64）
    """
    import base64
    if not password:
        return text
    key = hashlib.sha256(password.encode('utf-8')).digest()
    data = text.encode('utf-8')
    enc = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(enc).decode('ascii')


def decrypt_data(cipher, password):
    """解密 encrypt_data 的结果。"""
    import base64
    if not password:
        return cipher
    try:
        key = hashlib.sha256(password.encode('utf-8')).digest()
        enc = base64.b64decode(cipher.encode('ascii'))
        dec = bytes(b ^ key[i % len(key)] for i, b in enumerate(enc))
        return dec.decode('utf-8')
    except Exception:
        raise ValueError('密码错误或数据已损坏')


def save_config_encrypted(app_config, config_path, password):
    """加密保存配置。密码为空则普通保存。"""
    data = app_config.to_dict()
    data.setdefault('_comment', '角色及提成配置（已加密）')
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    if password:
        cipher = encrypt_data(json_text, password)
        payload = {'__encrypted__': True, 'data': cipher}
        json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    dir_path = os.path.dirname(config_path)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json',
                                     dir=dir_path, delete=False) as tmp:
        tmp.write(json_text)
        tmp_path = tmp.name
    try:
        os.replace(tmp_path, config_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return config_path


def load_config_encrypted(config_path, password=''):
    """加载配置；若检测到加密则需密码解密。"""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'配置文件不存在: {config_path}')
    with open(config_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    if isinstance(raw, dict) and raw.get('__encrypted__'):
        if not password:
            raise ValueError('配置文件已加密，请输入密码')
        decrypted = decrypt_data(raw.get('data', ''), password)
        raw = json.loads(decrypted)
    return _parse_config_dict(raw, config_path)


# ===================== 配置迁移（L） =====================

def migrate_config(raw):
    """将旧版 config 迁移到当前结构。

    兼容旧字段名：
    - '规则' / 'rule' / 'rules' → rules
    - '人员' / '人员配置' / '人员角色表' → 人员角色
    - '分组' / '组' → 小组
    - '排序' → 人员排序

    Args:
        raw: 原始 config dict

    Returns:
        (migrated_dict, changed_keys: list[str])
    """
    if not isinstance(raw, dict):
        return raw, []
    changed = []

    # 规则迁移
    if 'rules' not in raw:
        for old_key in ['规则', 'rule']:
            if old_key in raw and isinstance(raw[old_key], dict):
                raw['rules'] = raw[old_key]
                changed.append(old_key)
                break
    # 人员角色迁移
    if '人员角色' not in raw:
        for old_key in ['人员', '人员配置', '人员角色表']:
            if old_key in raw and isinstance(raw[old_key], dict):
                raw['人员角色'] = raw[old_key]
                changed.append(old_key)
                break
    # 小组迁移
    if '小组' not in raw:
        for old_key in ['分组', '组']:
            if old_key in raw and isinstance(raw[old_key], dict):
                raw['小组'] = raw[old_key]
                changed.append(old_key)
                break
    # 排序迁移
    if '人员排序' not in raw:
        for old_key in ['排序', 'order']:
            if old_key in raw and isinstance(raw[old_key], list):
                raw['人员排序'] = raw[old_key]
                changed.append(old_key)
                break
    return raw, changed
