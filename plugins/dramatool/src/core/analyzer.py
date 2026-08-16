from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from models.episode import RenameItem

# ---------------------------------------------------------------------------
# 集数识别
# ---------------------------------------------------------------------------


def infer_episode_number(name: str) -> int | None:
    normalized = name.replace("\\", "/")

    season_episode_match = re.search(r"S(\d+)E(\d+)", normalized, re.IGNORECASE)
    if season_episode_match:
        return int(season_episode_match.group(2))

    patterns = [
        r"第\s*(\d{1,3})\s*集",
        r"(?:^|[^A-Za-z])EP(?:ISODE)?\s*(\d{1,3})(?![A-Za-z])",
        r"(?:^|[^A-Za-z])E(\d{1,3})(?![A-Za-z])",
        r"(?:^|[._\s-])(\d{1,3})(?:$|[._\s-])",
        r"(\d{1,3})集",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            if value <= 999:
                return value
    return None


def build_target_path(source: Path, episode: int, output_dir: Path) -> Path:
    suffix = source.suffix
    new_stem = f"{episode:02d}"
    return output_dir / f"{new_stem}{suffix}"


def infer_episode_with_split(name: str) -> Tuple[int | None, int | None]:
    normalized = name.replace("\\", "/")
    split_match = re.search(r"(\d{1,3})[-_.](\d{1,3})(?![A-Za-z])", normalized)
    if split_match:
        return int(split_match.group(1)), int(split_match.group(2))
    episode = infer_episode_number(name)
    return episode, None


# ---------------------------------------------------------------------------
# build_rename_plan 及其子函数
# ---------------------------------------------------------------------------

_SKIP_DIR_NAMES = {"拆集后", "拆集", "4.工程截图"}


def _discover_version_dirs(folder: Path) -> List[Path]:
    """返回 folder 下的非 overlay 子目录；若无子目录则返回 folder 自身。"""
    dirs = [p for p in sorted(folder.iterdir())
            if p.is_dir()
            and p.name not in _SKIP_DIR_NAMES
            and not p.name.endswith("_renamed")]
    return dirs if dirs else [folder]


def _discover_overlay_dirs(folder: Path) -> List[Path]:
    """返回 folder 下存在的 overlay 目录（"拆集后"/"拆集"）。"""
    result: List[Path] = []
    for name in ("拆集后", "拆集"):
        overlay_dir = folder / name
        if overlay_dir.is_dir():
            result.append(overlay_dir)
    return result


def _collect_candidates(
    version_dir: Path,
    overlay_dirs: List[Path],
) -> List[Tuple[Path, int, int | None, Path]]:
    """从 version_dir 及其 overlay 目录中收集候选文件。"""
    candidates: List[Tuple[Path, int, int | None, Path]] = []

    for path in sorted(version_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(path.is_relative_to(ov) for ov in overlay_dirs):
            continue
        episode, split_part = infer_episode_with_split(path.name)
        if episode is None:
            continue
        candidates.append((path, episode, split_part, version_dir))

    for overlay_dir in overlay_dirs:
        candidate_dirs: List[Path] = []
        if version_dir != version_dir.parent:
            candidate_dirs.append(overlay_dir / version_dir.name)
        candidate_dirs.append(overlay_dir)
        for overlay_candidate_dir in candidate_dirs:
            if not overlay_candidate_dir.is_dir():
                continue
            for path in sorted(overlay_candidate_dir.rglob("*")):
                if not path.is_file():
                    continue
                episode, split_part = infer_episode_with_split(path.name)
                if episode is None:
                    continue
                candidates.append((path, episode, split_part, overlay_candidate_dir))
            break

    return candidates


def _resolve_target_dir(
    version_dir: Path,
    source_dir: Path,
    source_path: Path,
    folder: Path,
    resolved_output_dir: Path,
) -> Path:
    """计算某个候选文件的目标输出目录。"""
    relative_path = source_path.relative_to(source_dir)
    if version_dir == folder:
        return resolved_output_dir if relative_path.parent == Path(".") else resolved_output_dir / relative_path.parent
    if relative_path.parent == Path("."):
        return resolved_output_dir / version_dir.name
    return resolved_output_dir / version_dir.name / relative_path.parent


def _build_split_merge_items(
    candidates: List[Tuple[Path, int, int | None, Path]],
    version_dir: Path,
    folder: Path,
    resolved_output_dir: Path,
) -> List[RenameItem]:
    items: List[RenameItem] = []
    episode_groups: dict[int, List[Tuple[Path, int | None, Path]]] = {}
    for path, episode, split_part, source_dir in candidates:
        episode_groups.setdefault(episode, []).append((path, split_part, source_dir))

    sequence_counter = 0
    for episode in sorted(episode_groups):
        grouped_entries = episode_groups[episode]
        split_entries = [e for e in grouped_entries if e[1] is not None]
        if split_entries:
            selected = sorted(split_entries, key=lambda e: e[1] or 0)
        else:
            originals = [e for e in grouped_entries if e[2] == version_dir and e[1] is None]
            selected = originals or grouped_entries

        for path, _, source_dir in selected:
            target_dir = _resolve_target_dir(version_dir, source_dir, path, folder, resolved_output_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            sequence_counter += 1
            items.append(RenameItem(
                source=path,
                target=build_target_path(path, sequence_counter, target_dir),
                episode=sequence_counter,
            ))

    return items


def _build_normal_items(
    version_dir: Path,
    folder: Path,
    resolved_output_dir: Path,
) -> List[RenameItem]:
    items: List[RenameItem] = []
    sequence_counter = 0

    for path in sorted(version_dir.rglob("*")):
        if not path.is_file():
            continue
        if infer_episode_number(path.name) is None:
            continue
        target_dir = _resolve_target_dir(version_dir, version_dir, path, folder, resolved_output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        sequence_counter += 1
        items.append(RenameItem(
            source=path,
            target=build_target_path(path, sequence_counter, target_dir),
            episode=sequence_counter,
        ))

    return items


def build_rename_plan(
    folder: Path,
    output_dir: Path | None = None,
    mode: str = "split_merge",
    split_source_dir: Path | None = None,
) -> List[RenameItem]:
    resolved_output_dir = output_dir or folder.with_name(f"{folder.name}_renamed")

    version_dirs = _discover_version_dirs(folder)
    overlay_dirs = _discover_overlay_dirs(folder)
    if split_source_dir is not None and split_source_dir.is_dir():
        overlay_dirs = [split_source_dir]

    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    # 排除输出目录（可能因之前的扫描调用而被误认为版本目录）
    resolved_abs = resolved_output_dir.resolve()
    version_dirs = [d for d in version_dirs if d.resolve() != resolved_abs]

    items: List[RenameItem] = []
    for version_dir in version_dirs:
        version_output_dir = resolved_output_dir / version_dir.name if version_dir != folder else resolved_output_dir
        version_output_dir.mkdir(parents=True, exist_ok=True)

        candidates = _collect_candidates(version_dir, overlay_dirs)
        if not candidates:
            continue

        if mode == "split_merge" and any(split_part is not None for _, _, split_part, _ in candidates):
            items.extend(_build_split_merge_items(candidates, version_dir, folder, resolved_output_dir))
        else:
            items.extend(_build_normal_items(version_dir, folder, resolved_output_dir))

    return items
