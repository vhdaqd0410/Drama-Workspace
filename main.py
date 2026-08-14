# -*- coding: utf-8 -*-
"""视频工作台 v2.0 — 统一启动入口。

双击 start.bat / start.vbs 或命令行: python main.py
"""
import os
import sys
import webbrowser
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# 确保 backend 包可导入
backend_dir = os.path.join(BASE_DIR, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def open_browser_later(url, delay=2.5):
    """延迟打开浏览器。"""
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()


def check_dependencies():
    """检查关键依赖是否安装。"""
    missing = []
    for pkg_name, import_name in [
        ("flask", "flask"),
        ("numpy", "numpy"),
        ("opencv-python", "cv2"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(f"\n⚠ 缺少依赖: {', '.join(missing)}")
        print(f"  请运行: pip install {' '.join(missing)}")
        print()
    return missing


def main():
    # 检查依赖
    missing = check_dependencies()

    # 导入配置和应用
    from backend import config
    from backend.app import create_app

    cfg = config.load_config()
    app = create_app()

    host = cfg.get("server", {}).get("host", "127.0.0.1")
    port = cfg.get("server", {}).get("port", 8089)
    debug = cfg.get("server", {}).get("debug", False)

    url = f"http://{host}:{port}/"

    # 延迟打开浏览器
    open_browser_later(url)

    print()
    print("=" * 60)
    print("  🎬 视频工作台 v2.0")
    print("  📦 统一集成: 项目管理 + NAS同步 + 分集 + 质检")
    print("=" * 60)
    print(f"  🌐 访问地址: {url}")
    print(f"  📁 工作目录: {BASE_DIR}")
    print(f"  💾 数据库:   {config.DB_PATH}")
    print(f"  📝 配置文件: {config.CONFIG_PATH}")
    if missing:
        print(f"  ⚠  缺少依赖: {', '.join(missing)}")
    print("=" * 60)
    print("  按 Ctrl+C 退出")
    print()

    try:
        try:
            import waitress
            waitress.serve(app, host=host, port=port, threads=8)
        except ImportError:
            app.run(host=host, port=port, debug=debug, use_reloader=False)
    except KeyboardInterrupt:
        print("\n👋 已停止")


if __name__ == "__main__":
    main()
