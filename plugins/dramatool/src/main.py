from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def run(headless: Optional[bool] = None) -> int:
    """启动 DramaTool。

    默认优先尝试显示 GUI；若当前环境不支持 Tkinter 或窗口无法创建，
    则自动退回到无界面模式，并输出更明确的提示。
    """
    if headless is None:
        headless = os.environ.get("DRAMATOOL_HEADLESS") == "1"

    if headless:
        print("DramaTool 已在无界面模式启动。")
        return 0

    try:
        import tkinterdnd2
        from ui.main_window import MainWindow
    except Exception as exc:  # pragma: no cover - 依赖环境差异
        print(f"无法创建界面，已切换到无界面模式：{exc}")
        return 0

    try:
        root = tkinterdnd2.Tk()
        root.withdraw()
        root.update_idletasks()
        root.deiconify()
    except Exception as exc:
        print(f"创建 Tkinter 窗口失败：{exc}")
        return 0

    app = MainWindow(root=root)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
