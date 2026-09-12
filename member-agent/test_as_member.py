# -*- coding: utf-8 -*-
r"""组员端测试向导 —— 在你自己的电脑上模拟组员。

做三件事：
  1. 连本地 dev 主端(8090)，选一个真实项目里真实有分集的人
  2. 用该人姓名 + 令牌 + 临时本地目录配置并启动本地助手(8091)
  3. 打开浏览器，你看到/操作的就是组员视角

不需要联网、不影响生产数据（全部在 F 盘 dev 环境）。
"""
import os
import sys
import json
import time
import socket
import sqlite3
import subprocess
import webbrowser

DEV = r"F:\OH-WorkSpace\projects\视频工作台-dev"
AGENT = os.path.join(DEV, "member-agent")
PY = sys.executable
MAIN_PORT = 8090
AGENT_PORT = 8091
TEST_ROOT = os.path.join(DEV, "data", "_组员测试项目")


def listening(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def pick_member():
    """从 dev 库里找一个「真实项目 + 真实负责某剧集数的人」组合。"""
    conn = sqlite3.connect(os.path.join(DEV, "data", "workbench.db"))
    rows = conn.execute(
        "SELECT name, episode_plan FROM projects "
        "WHERE custom_status IN ('剪辑中','审核中','修改中') "
        "AND episode_plan IS NOT NULL AND episode_plan NOT IN ('','{}') "
        "ORDER BY id DESC LIMIT 60"
    ).fetchall()
    total = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    conn.close()

    from collections import Counter
    for name, plan in rows:
        try:
            pl = json.loads(plan)
        except Exception:
            continue
        ppl = [str(v).strip() for v in pl.values() if str(v).strip()]
        if not ppl:
            continue
        # 选集数最少的人，拉素材快
        ed, n = Counter(ppl).most_common()[-1]
        return name, ed, n, total
    return None, None, 0, total


def get_key():
    import yaml
    with open(os.path.join(DEV, "backend", "config.yaml"), encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("web", {}).get("api_secret", "")


def main():
    print("=" * 58)
    print("  组员端测试向导")
    print("=" * 58)

    if not listening(MAIN_PORT):
        print("\n[!] dev 主端没在运行（%d 端口）" % MAIN_PORT)
        print("    请先双击 F:\\OH-WorkSpace\\projects\\视频工作台-dev\\start_browser.bat")
        print("    等它启动后，再运行本向导。")
        return 1

    print("\n[1/3] dev 主端已在运行 (%d) ✓" % MAIN_PORT)

    name, editor, eps, total = pick_member()
    if not name:
        print("\n[!] dev 库里没找到可用的分集数据，无法模拟。")
        return 1
    print("[2/3] 已选测试组合：")
    print("      项目：%s" % name[:50])
    print("      组员：%s（负责 %d 集）" % (editor, eps))

    # 确保该组员有令牌
    sys.path.insert(0, DEV)
    sys.path.insert(0, os.path.join(DEV, "backend"))
    os.chdir(DEV)
    import importlib
    app_mod = importlib.import_module("app")
    member_auth = importlib.import_module("member_auth")
    db = app_mod.db
    db.add_member(editor, role="editor")
    tok = member_auth.new_token()
    db.set_member_token(editor, tok, client_role="member")
    member_auth.reload_cache(db)
    print("      已发放令牌：%s..." % tok[:16])

    # 写助手配置
    os.makedirs(TEST_ROOT, exist_ok=True)
    cfg = {
        "server_url": "http://127.0.0.1:%d" % MAIN_PORT,
        "api_key": tok,
        "member_name": editor,
        "local_root": TEST_ROOT,
        "open_pr": False,
    }
    with open(os.path.join(AGENT, "member_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("      本地项目目录：%s" % TEST_ROOT)

    # 启动助手
    print("\n[3/3] 启动本地助手 (%d)..." % AGENT_PORT)
    if listening(AGENT_PORT):
        print("      助手已在运行，直接打开页面")
    else:
        log = open(os.path.join(AGENT, "_run.log"), "w", encoding="utf-8")
        subprocess.Popen([PY, "-X", "utf8", "member_agent.py"], cwd=AGENT,
                         stdout=log, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for _ in range(30):
            time.sleep(0.5)
            if listening(AGENT_PORT):
                break

    if not listening(AGENT_PORT):
        print("      [X] 助手启动失败，看看 %s" % os.path.join(AGENT, "_run.log"))
        return 1

    url = "http://127.0.0.1:%d/" % AGENT_PORT
    print("\n" + "=" * 58)
    print("  就绪！浏览器地址：%s" % url)
    print("=" * 58)
    print("""
你现在看到的**就是组员视角**：
  · 只有「项目看板」（其他 Tab 都被隐藏）
  · 项目卡片上有打勾按钮
  · 点「创建本地项目」会把素材拉到：
      %s

想验证什么：
  1. 打开协作卡片，点一下打勾 → 换回主端(8090)的「协作」Tab 看是否同步
  2. 点某个项目的「创建本地项目」→ 看本地目录是否真的出现素材

注意：这是测试环境，令牌和数据都在 F 盘 dev 目录。
""" % TEST_ROOT)

    webbrowser.open(url)
    input("\n按回车结束（助手会继续在后台运行，要停止请关掉 python 进程）...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
