from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenameItem:
    source: Path
    target: Path
    episode: int
