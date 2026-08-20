# -*- coding: utf-8 -*-
"""重启视频工作台桌面版。

用法：
  python restart_software.py            # 停止并重新启动（默认启动方式）
  python restart_software.py --no-start # 只停止不重启

步骤：
  1. 调用 http://127.0.0.1:8089/api/quit 优雅退出（若在运行）
  2. 等待端口释放（超时 8 秒），强杀残留进程
  3. 等待 0.5 秒后，用 pythonw 无窗口重新启动 main_desktop.py
"""
import os, sys, time, subprocess, socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_PORT = 8089
PROC_NAME = "main_desktop.py"


def _port_alive(port, timeout=0.4):
    try:
        s = socket.socket()
        s.settimeout(timeout)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


def _kill_desktop_procs():
    """杀掉正在运行的 main_desktop.py 进程。"""
    try:
        out = subprocess.run(
            ["wmic", "process", "where",
             f"name like '%python%' and CommandLine like '%{PROC_NAME}%'",
             "get", "ProcessId", "/format:csv"],
            capture_output=True, text=True, timeout=10)
        pids = set()
        for line in (out.stdout or "").splitlines():
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[-1].strip().isdigit():
                pids.add(int(parts[-1].strip()))
        for pid in pids:
            try:
                os.kill(pid, 9)
                print(f"  强杀进程 PID {pid}")
            except Exception:
                pass
        return len(pids)
    except Exception as e:
        print(f"  查找进程失败: {e}")
        return 0


def graceful_quit():
    """优先通过 API 优雅退出。"""
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{SERVER_PORT}/api/quit",
                                     method="POST")
        urllib.request.urlopen(req, timeout=3)
        print("  已请求 /api/quit 优雅退出")
        return True
    except Exception:
        return False


def main():
    do_start = "--no-start" not in sys.argv

    if _port_alive(SERVER_PORT):
        print("检测到软件正在运行，准备退出...")
        ok = graceful_quit()
        # 等待端口释放（优雅退出需 2s）
        waited = 0
        while _port_alive(SERVER_PORT) and waited < 8:
            time.sleep(0.4)
            waited += 0.4
        if _port_alive(SERVER_PORT):
            print("  优雅退出未完成，强制结束残留进程...")
            _kill_desktop_procs()
            time.sleep(0.5)
        else:
            print("  软件已优雅退出")
    else:
        print("软件未在运行")

    if not do_start:
        print("完成（仅停止，不重启）")
        return

    # 确保端口完全释放
    time.sleep(0.5)
    print("重新启动软件...")
    pythonw = os.path.join(
        os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = os.path.join(BASE_DIR, "main_desktop.py")
    subprocess.Popen([pythonw, script], cwd=BASE_DIR,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    print("软件已启动（无黑窗）")


if __name__ == "__main__":
    main()
