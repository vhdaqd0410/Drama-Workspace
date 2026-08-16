from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Tuple

from core.merger import copy_files


def run_rename_task(
    pairs: List[Tuple[Path, Path]],
    should_cancel: Callable[[], bool],
    should_pause: Callable[[], bool],
    on_progress: Callable[[int, Path, Path, bool, Exception | None], None],
    on_complete: Callable[[bool], None],
) -> None:
    """Execute a batch of file copies with pause and cancel support.

    Intended to run on a background thread.  Pause checks happen before
    every file; cancel checks happen before and during pause waits.
    """

    for index, (source, target) in enumerate(pairs, start=1):
        while should_pause():
            if should_cancel():
                on_complete(True)
                return
            time.sleep(0.1)

        if should_cancel():
            on_complete(True)
            return

        try:
            copy_files([(source, target)])
            on_progress(index, source, target, True, None)
        except Exception as exc:
            on_progress(index, source, target, False, exc)

    on_complete(False)
