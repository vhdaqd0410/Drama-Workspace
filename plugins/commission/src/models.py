# -*- coding: utf-8 -*-
"""AI后期剪辑提成工具 — 数据模型（dataclass + 类型注解）

为所有核心数据结构提供类型安全的定义，配合 mypy/pyright 可获得静态检查。
所有模型均为纯数据容器，不包含业务逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import Any, Iterator, Optional, Union

import constants as C


# ===================== 配置模型 =====================

@dataclass
class QuotaRule:
    """角色的提成计算规则"""
    quota: int = 0                     # 基准集数（0 表示无限制，如组长）
    over_price: int = 0                # 超额每集单价
    short_penalty: int = 0             # 缺集每集扣除
    eps_price: int = 0                 # 每集单价（组长用）
    project_bonus: int = 0             # 组内每部提成（组长用）
    description: str = ""              # 提成构成描述

    @classmethod
    def from_config(cls, role: str, rule_dict: dict) -> "QuotaRule":
        """从 config.json 的 rules 节解析"""
        if role == C.ROLE_LEADER:
            return cls(
                quota=0,
                eps_price=rule_dict.get("每集单价", C.DEFAULT_LEADER_EPS_PRICE),
                project_bonus=rule_dict.get("组内每部提成", C.DEFAULT_LEADER_PROJECT_BONUS),
                description=rule_dict.get("提成构成描述", ""),
            )
        return cls(
            quota=rule_dict.get("基准集数", C.DEFAULT_CARD1_QUOTA if role == C.ROLE_CARD1 else C.DEFAULT_CARD2_QUOTA),
            over_price=rule_dict.get("超额每集", C.DEFAULT_CARD1_OVER_PRICE),
            short_penalty=rule_dict.get("缺集每集扣", C.DEFAULT_CARD1_SHORT_PENALTY),
            description=rule_dict.get("提成构成描述", ""),
        )


@dataclass
class GroupInfo:
    """小组信息"""
    leader: str = ""
    members: list[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, data: dict) -> "GroupInfo":
        return cls(
            leader=data.get("组长", ""),
            members=list(data.get("成员", [])),
        )


@dataclass
class AppConfig:
    """完整配置（config.json 的 Python 表示）"""
    person_roles: dict[str, str] = field(default_factory=dict)   # name -> role
    rules: dict[str, QuotaRule] = field(default_factory=dict)    # role -> QuotaRule
    groups: dict[str, GroupInfo] = field(default_factory=dict)   # group_name -> GroupInfo
    person_order: list[str] = field(default_factory=list)         # 输出排序
    personnel_templates: dict[str, list[str]] = field(default_factory=dict)  # 选人模版
    app_settings: dict[str, Any] = field(default_factory=dict)    # GUI 上次使用设置
    theme: str = "light"                                        # 界面主题 light/dark
    monthly_goals: dict[str, Any] = field(default_factory=dict)  # 月度目标
    project_templates: dict[str, Any] = field(default_factory=dict)  # 智能分集项目模板
    version: str = "1.0.0"                                        # 当前版本号
    update_check: bool = True                                     # 是否检查更新
    favorites: list[str] = field(default_factory=list)            # 常用操作收藏

    @property
    def all_names(self) -> list[str]:
        return list(self.person_roles.keys())

    def get_role(self, name: str) -> str:
        raw = self.person_roles.get(name, "")
        return normalize_role(raw)

    def get_rule(self, name: str) -> QuotaRule:
        role = self.get_role(name)
        return self.rules.get(role, QuotaRule())

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """从 config.json 字典构建 AppConfig，带容错"""
        # 解析 rules
        rules: dict[str, QuotaRule] = {}
        raw_rules = data.get("rules", {}) if isinstance(data, dict) else {}
        for role in [C.ROLE_CARD1, C.ROLE_CARD2, C.ROLE_ASSISTANT, C.ROLE_LEADER]:
            rd = raw_rules.get(role, {})
            rules[role] = QuotaRule.from_config(role, rd)

        # 解析 groups
        groups: dict[str, GroupInfo] = {}
        raw_groups = data.get("小组", {}) if isinstance(data, dict) else {}
        for gname, gdata in raw_groups.items():
            groups[gname] = GroupInfo.from_config(gdata)

        return cls(
            person_roles=dict(data.get("人员角色", {})),
            rules=rules,
            groups=groups,
            person_order=list(data.get("人员排序", [])),
            personnel_templates={
                str(k): list(v) for k, v in data.get("personnel_templates", {}).items()
            },
            app_settings=dict(data.get("app_settings", {})),
            theme=data.get("theme", "light"),
            monthly_goals=dict(data.get("monthly_goals", {})),
            project_templates=dict(data.get("project_templates", {})),
            version=data.get("version", "1.0.0"),
            update_check=bool(data.get("update_check", True)),
            favorites=list(data.get("favorites", [])),
        )

    def to_dict(self) -> dict:
        """序列化回 config.json 格式"""
        rules_out: dict[str, dict] = {}
        for role, qr in self.rules.items():
            if role == C.ROLE_LEADER:
                rules_out[role] = {
                    "每集单价": qr.eps_price,
                    "组内每部提成": qr.project_bonus,
                    "提成构成描述": qr.description,
                }
            else:
                rules_out[role] = {
                    "基准集数": qr.quota,
                    "超额每集": qr.over_price,
                    "缺集每集扣": qr.short_penalty,
                    "提成构成描述": qr.description,
                }

        groups_out: dict[str, dict] = {}
        for gname, gi in self.groups.items():
            groups_out[gname] = {"组长": gi.leader, "成员": gi.members}

        return {
            "rules": rules_out,
            "人员角色": dict(self.person_roles),
            "小组": groups_out,
            "人员排序": list(self.person_order),
            "personnel_templates": dict(self.personnel_templates),
            "app_settings": dict(self.app_settings),
            "theme": self.theme,
            "monthly_goals": dict(self.monthly_goals),
            "project_templates": dict(self.project_templates),
            "version": self.version,
            "update_check": self.update_check,
            "favorites": list(self.favorites),
        }


# ===================== 项目记录 =====================

@dataclass
class ProjectRecord:
    """单条项目分配记录（一行数据）"""
    person_name: str = ""              # 人员姓名
    role: str = ""                     # 标准化角色
    project_id: str = ""               # 项目ID（4位数字）
    project_type: str = "AI海外真人"   # 项目类型
    project_name: str = ""             # AI项目名称
    start_date: Optional[date] = None  # 开始日期
    end_date: Optional[date] = None    # 结束日期
    detail: str = ""                   # 完成明细（逗号分隔集数）
    episode_count: int = 0             # 有效集数（含超时加权）
    original_count: int = 0            # 原始集数（不含加权）
    overtime_count: int = 0            # 超时集数（每个算额外+1）
    overtime_detail: list[int] = field(default_factory=list)  # 超时集号列表

    @property
    def has_overtime(self) -> bool:
        return self.overtime_count > 0


# ===================== 提成计算结果 =====================

@dataclass
class CommissionResult:
    """单人提成计算结果"""
    person_name: str = ""
    role: str = ""
    total_episodes: int = 0            # 当月总集数
    quota: int = 0                     # 基准集数（0=无限制）
    is_complete: str = ""              # "是" / "否" / "N/A"
    overtime_bonus: int = 0            # 超额提成金额
    shortage_penalty: int = 0          # 缺集扣除金额
    group_project_bonus: int = 0       # 组长组内项目提成
    total_commission: int = 0          # 提成合计
    description: str = ""              # 提成构成描述
    rule: QuotaRule = field(default_factory=QuotaRule)

    @property
    def is_leader(self) -> bool:
        return self.role == C.ROLE_LEADER

    @property
    def extra_total(self) -> int:
        return self.overtime_bonus + self.group_project_bonus


# ===================== 统计摘要 =====================

@dataclass
class SummaryStats:
    """月度统计摘要"""
    total_people: int = 0
    total_projects: int = 0
    total_episodes: int = 0
    total_commission: int = 0
    done_count: int = 0                 # 达标人数
    fail_count: int = 0                 # 未达标人数
    card1_count: int = 0               # 一卡人数
    card2_count: int = 0               # 二卡人数
    project_list: list[dict] = field(default_factory=list)
    person_list: list[dict] = field(default_factory=list)


# ===================== 数据预览 =====================

@dataclass
class PersonPreview:
    """数据预览中单人的汇总信息"""
    name: str = ""
    role: str = ""
    episodes: int = 0
    projects: int = 0
    quota: int = 0
    status: str = ""
    commission: int = 0


# ===================== 工具函数 =====================

def normalize_role(role_str: str) -> str:
    """容错：将各种角色名规范化为标准名"""
    if not role_str:
        return C.ROLE_CARD1
    s = role_str.strip()
    if "一卡" in s:
        return C.ROLE_CARD1
    if "二卡" in s:
        return C.ROLE_CARD2
    if "助理" in s:
        return C.ROLE_ASSISTANT
    if "小组长" in s:
        return C.ROLE_CARD1  # 小组长和一卡计算方式一样
    if "组长" in s:
        return C.ROLE_LEADER
    return C.ROLE_CARD1


def safe_int(value: Any, default: int = 0) -> int:
    """安全转换为 int，失败返回 default"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float，失败返回 default"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def iter_records_by_person(
    records: list[ProjectRecord],
    order: Optional[list[str]] = None,
) -> Iterator[tuple[str, list[ProjectRecord]]]:
    """按人员分组迭代记录，尊重排序"""
    grouped: dict[str, list[ProjectRecord]] = {}
    for r in records:
        grouped.setdefault(r.person_name, []).append(r)

    names = order or sorted(grouped.keys())
    for name in names:
        if name in grouped:
            yield name, grouped[name]
