from pathlib import Path
from typing import List, Sequence, Tuple
import shutil


def copy_file(source: Path | str, target: Path | str) -> Path:
    """Copy a file to a target path without changing the source file.

    The target may be in the same directory as the source. In that case,
    a plain copy is still fine. When the target lives in a different
    directory, the parent directories are created first.
    """

    source_path = Path(source)
    target_path = Path(target)

    if source_path == target_path:
        return target_path

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    return target_path


def copy_files(pairs: Sequence[Tuple[Path | str, Path | str]]) -> List[Path]:
    """Copy a batch of files to new paths while preserving the originals."""

    return [copy_file(source, target) for source, target in pairs]
