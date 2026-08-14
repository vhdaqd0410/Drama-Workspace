import sys, os, json, shutil
sys.path.insert(0, "backend")
os.environ["DRAMA_DESKTOP"] = "1"

from app import create_app
app = create_app()

with app.test_client() as c:
    from app import sync_engine, db

    # 找一个有 000交付 目录 + 有制作部路径的项目
    projs = db.get_all_projects()
    test = None
    for p in projs:
        gp = p.get("group_path", "")
        pp = p.get("production_path", "")
        deliver_dir = os.path.join(gp, "000交付") if gp else ""
        if gp and pp and os.path.isdir(deliver_dir):
            test = p
            break

    if not test:
        print("❌ 没找到测试项目（需要 group_path + production_path + 000交付）")
    else:
        name = test["name"]
        gp = test["group_path"]
        pp = test["production_path"]
        deliver_dir = os.path.join(gp, "000交付")
        prod_deliver = os.path.join(pp, "000交付")

        print(f"测试项目: {name}")
        print(f"组内 000交付: {deliver_dir}")
        print(f"制作部 000交付: {prod_deliver}")
        print(f"制作部 000交付 存在? {os.path.isdir(prod_deliver)}")

        # 1. 测试 list_files?mode=delivery — 看 folders 有哪些
        resp = c.get(f"/api/project/{name}/list_files?mode=delivery")
        data = resp.get_json()
        folders = [f["name"] for f in data.get("folders", [])]
        files_count = len(data.get("files", []))
        print(f"\n📂 delivery 模式列出: folders={folders}, files={files_count}")

        # 2. 测试 API 路由 mode=delivery 分支
        if folders:
            test_folder = folders[0]
            print(f"\n🌀 测试 /api/deliver_folder mode=delivery, folder={test_folder}")

            # 状态先改成"待交付"
            db.update_project_custom_status(name, "待交付")

            # 调后端函数（不通过 HTTP，避免 Shell 复制弹框阻止测试）
            ok, msg = sync_engine.deliver_delivery_folder(name, test_folder)
            print(f"deliver_delivery_folder -> ok={ok}, msg={msg}")

            # 验证状态变"待质检"
            proj2 = db.get_project(name)
            status2 = proj2.get("custom_status", "")
            print(f"📊 状态 -> {status2} {'✅' if status2 == '待质检' else '❌ 应为 待质检'}")

            # 验证文件已复制
            prod_src = os.path.join(deliver_dir, test_folder)
            prod_dst = os.path.join(prod_deliver, test_folder)
            if os.path.isdir(prod_dst):
                print(f"✅ 目标文件夹存在: {prod_dst}")
            else:
                print(f"❌ 目标文件夹不存在: {prod_dst}")
        else:
            print("⚠️ 没有 folders 可测试")

        print("\n🏁 测试完成")
