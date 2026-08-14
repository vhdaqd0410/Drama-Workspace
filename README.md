<div align="center">

# 🎬 视频工作台

### AI 漫剧生产流程一站式管理平台

[![Python](https://img.shields.io/badge/python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.5+-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/status-active-brightgreen?style=for-the-badge)]()
[![Version](https://img.shields.io/badge/v2.1-blue?style=for-the-badge)]()

📡 **实时扫描 · 可视化进度 · 智能协作 · 一键交付**

</div>

---

<div align="center">
  <table>
    <tr>
      <td align="center" width="16%">
        <h3>📁</h3>
        <b>磁盘驱动</b><br/>NAS 自动发现
      </td>
      <td align="center" width="16%">
        <h3>📊</h3>
        <b>进度可视化</b><br/>实时缺集扫描
      </td>
      <td align="center" width="16%">
        <h3>🎥</h3>
        <b>视频预览</b><br/>浏览器直接播
      </td>
      <td align="center" width="16%">
        <h3>💻</h3>
        <b>系统原生复制</b><br/>Shell.Application
      </td>
      <td align="center" width="16%">
        <h3>🔍</h3>
        <b>AI 质检</b><br/>黑帧/花屏检测
      </td>
      <td align="center" width="16%">
        <h3>📅</h3>
        <b>月份统计</b><br/>按项目归档
      </td>
    </tr>
  </table>
</div>

---

## 📑 目录

- [✨ 功能一览](#-功能一览)
- [🏗️ 系统架构](#️-系统架构)
- [📂 项目结构](#-项目结构)
- [🚀 快速开始](#-快速开始)
- [🧩 界面预览](#-界面预览)
- [🔌 API 接口](#-api-接口)
- [🗄️ 数据库](#️-数据库)
- [🧪 开发指南](#-开发指南)
- [🐛 常见问题](#-常见问题)
- [📜 依赖 & 日志](#-依赖--日志)
- [🗺️ 路线图](#️-路线图)
- [📄 License](#-license)

---

## ✨ 功能一览

### 工作流全支持

```
📋 分集中 → ✂️ 剪辑中 → 👀 审核中 → ✏️ 修改中 → 📦 交付中 → 🔍 质检中 → ✅ 已完成
```

> 9 种状态 · 可视化工作流进度条 · 点击卡片状态下拉框即可切换 · 自动按工作流步数重排序

### 核心能力

| 模块 | 说明 |
|------|------|
| 🔎 NAS 自动扫描 | N 盘制作部 + O 盘组NAS 双源扫描，项目自动按部门分组 |
| 📊 分集管理 | Chips 可视化分配 · 批量粘贴 · 自动均分 · 工作量柱状图 · 历史复用 |
| 📈 进度扫描 | 自动扫描 `01上映单集版` 目录，缺集红色高亮 + 实时百分比 |
| 🎥 成片预览 | editing/revising/delivery 三模式 · 跨盘 fallback · 倍速播放 · 步进 |
| 💻 系统原生复制 | **Shell.Application.CopyHere** 弹系统资源管理器进度对话框，用户可见 |
| 📦 素材/成片回传 | 批量回传共用一个 CopyHere 窗口（临时目录硬链接合并） |
| 📅 项目月份 | 下拉框选择月份（前后各 1 年）· localStorage 持久化 · 按名称去重统计 |
| 🔍 视频质检 | OpenCV 黑帧检测 · 花屏检测 · PSNR/SSIM · 音轨存在性 · 生成 HTML 报告 |
| 👥 团队管理 | 成员 CRUD · 职位下拉（组长/卡前/卡后/助理）· 部门归属 · 集数自动移位 |
| 👀 Watchdog | 后台线程监听成片目录 · 稳定 30s 后自动标记 |
| 📑 Excel 导出 | 分集分配一键导出模板 · 自动备份 · 追加写入不覆盖 |
| 📝 修改预览 | 修改中的项目额外显示"📝 修改预览"按钮 |

---

## 🏗️ 系统架构

### 后端模块拆分（Mixin 继承）

```
app.py ─┬── scan.py      (ScanMixin)      — get_projects_enriched, 自动发现项目
        ├── sync.py      (SyncMixin)      — robocopy + Shell.Application.CopyHere
        ├── deliver.py   (DeliverMixin)   — 成片/修改/交付三场景回传
        └── preview.py   (PreviewMixin)   — 视频路径解析 + 流式预览路由

enhanced_routes.py   — 扩展路由（团队、分集导入、light 列表）
fenji.py / fenji_exporter.py — 分集分配 + Excel 导出
qa_engine.py + detection.py — 质检引擎（黑帧/花屏/PSNR/SSIM）
watcher.py           — Watchdog 后台线程
db.py                — SQLite ORM + 建表迁移
utils.py             — 共享工具函数
```

### 前端模块拆分

```
templates/index.html ── 骨架 HTML + 内联样式

static/js/
├── core.js              (420 行)   — Dashboard 渲染 / 月份统计 / 状态徽章
├── project.js           (234 行)   — 项目加载 / 月份 localStorage merge / 名称去重
├── episode.js           (598 行)   — 分集详情 / 缺集扫描 / setProjectMonth 下拉框
├── fenji-assign.js      (962 行)   — 分集 Chips 可视化分配 / 批量粘贴
├── fenji-init.js        (51 行)    — 分集初始化
├── deliverables.js      (329 行)   — 成片/修改预览面板
├── deliver-batch.js     (212 行)   — 批量回传进度
├── deliver-events.js    (183 行)   — 回传事件监听
├── deliver-patch.js     (3 行)     — 回传补丁
├── preview.js           (122 行)   — 视频预览弹窗
├── team.js              (197 行)   — 团队成员管理
├── qa.js                (80 行)    — 质检入口
└── app.js               (33 行)    — 应用初始化
```

### 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│ 浏览器                                                      │
│  index.html → 13 个 ES 模块（core / project / episode / ...）│
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/JSON
┌────────────────────▼────────────────────────────────────────┐
│ Flask 后端 0.0.0.0:8089  (waitress WSGI 生产模式)          │
│                                                             │
│  app.py (891行)                                             │
│  ├── /api/projects            → ScanMixin.get_projects     │
│  ├── /api/project_months      → SELECT project_month 专门接口│
│  ├── /api/project/<n>/update_month  → 月份下拉框持久化       │
│  ├── /api/project/<n>/episodes_status → 实时缺集扫描         │
│  ├── /api/preview/<n>/<f>     → PreviewMixin 流式视频       │
│  └── 30+ 其他路由                                            │
│                                                             │
│  enhanced_routes.py (514行)  fenji.py  qa_engine.py         │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ 存储层                                                       │
│                                                             │
│ 💾 SQLite (workbench.db)                                    │
│   projects / team_members / episode_plans / qa_records /   │
│   sync_log / delivery_records                                │
│                                                             │
│ 📁 NAS 磁盘                                                  │
│   N:\ 制作部 (多部门)    O:\ 组内NAS (剪辑一组)               │
│                                                             │
│ 🧠 浏览器 localStorage                                      │
│   wb_project_months: {项目名: '2026-08'}  ← 月份缓存         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
Drama-Workspace/
│
├── 🚀 main.py                     # 统一启动入口（自动打开浏览器）
├── 🛠️ start.bat / start.vbs       # Windows 一键启动
├── 📦 requirements.txt            # Python 依赖清单
├── 🔒 .gitignore                  # 排除 DB / 日志 / config.yaml / 临时脚本
├── 📖 README.md                   # 项目文档（本文件）
│
├── 🐍 backend/                    # ═══════ Python 后端 ═══════
│   ├── __init__.py                # 包初始化：导出 create_app / db
│   ├── app.py                     # Flask 主入口 + 38 个核心路由（891 行）
│   ├── enhanced_routes.py         # 扩展路由：团队 / 分集导入 / light 列表（514 行）
│   ├── scan.py ⭐ Mixin           # 项目扫描 + 按名称去重（374 行）
│   ├── sync.py ⭐ Mixin           # robocopy + Shell.Application.CopyHere（355 行）
│   ├── deliver.py ⭐ Mixin        # 成片/修改/交付 三场景回传（1493 行）
│   ├── preview.py ⭐ Mixin        # 视频路径解析 + 跨盘 fallback（235 行）
│   ├── sync_engine.py             # 兼容桥：从 app 导入 Mixin（23 行）
│   ├── db.py                      # SQLite ORM + 建表迁移（591 行）
│   ├── fenji.py                   # 分集分配逻辑（74 行）
│   ├── fenji_exporter.py          # Excel 模板导出 + 追加写入（131 行）
│   ├── qa_engine.py               # 视频质检引擎（460 行）
│   ├── detection.py               # OpenCV 黑帧/花屏/PSNR/SSIM（1244 行）
│   ├── watcher.py                 # Watchdog 后台线程（197 行）
│   ├── config.py                  # 配置加载 / 保存
│   ├── config.example.yaml        # 📋 配置模板（公开，不含真实路径）
│   ├── config.yaml                # ⚠️ 本地私有配置（已加入 .gitignore）
│   ├── utils.py                   # 共享工具函数
│   └── report_template.py         # 质检报告 HTML 模板
│
├── 🖥️ templates/
│   └── index.html                 # 单页应用骨架（707 行 · 样式内联）
│
├── 🧩 static/js/                  # ═══════ 前端模块化 ═══════
│   ├── core.js                    # Dashboard 渲染 / 月份统计 / 状态徽章
│   ├── project.js                 # 项目加载 / 名称去重 / localStorage merge
│   ├── episode.js                 # 缺集扫描 / setProjectMonth 下拉框 modal
│   ├── fenji-assign.js            # Chips 可视化分配
│   ├── fenji-init.js              # 分集初始化
│   ├── deliverables.js            # 成片/修改预览
│   ├── deliver-batch.js           # 批量回传进度
│   ├── deliver-events.js          # 回传事件监听
│   ├── deliver-patch.js           # 回传补丁
│   ├── preview.js                 # 视频预览弹窗
│   ├── team.js                    # 团队成员管理
│   ├── qa.js                      # 质检入口
│   └── app.js                     # 应用初始化
│
└── 💾 data/                       # ═══════ 运行时数据（自动生成）═══════
    ├── workbench.db               # SQLite 数据库
    └── config.json                # 前端运行时配置
```

---

## 🚀 快速开始

### 环境要求

| 项目 | 要求 |
|:---|:---|
| 🪟 操作系统 | Windows 10 / 11（依赖 `robocopy` + `Shell.Application`） |
| 🐍 Python | ≥ 3.8（推荐 3.10+） |
| 🌐 浏览器 | Chrome / Edge（视频预览需 HTML5 支持） |
| 🔌 网络 | 可访问 NAS 路径（N: 盘 / O: 盘） |

### 三步启动

```bash
# ① 克隆仓库
git clone https://github.com/vhdaqd0410/Drama-Workspace.git
cd Drama-Workspace

# ② 安装依赖
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

```yaml
# ③ 拷贝配置并修改（关键！）
# 复制 backend/config.example.yaml → backend/config.yaml
# 修改 nas.production_roots / nas.group_root 为你的实际 NAS 路径
# 可配置 PotPlayer 路径: players.potplayer_path
```

```bash
# ④ 启动（任选一种）
start.bat            # ⭐ 推荐：双击即可，自动打开浏览器
python main.py       # 命令行
start.vbs            # 后台静默启动（无 CMD 窗口）
```

### 启动成功

```
============================================================
  🎬 视频工作台 v2.0
  📦 统一集成: 项目管理 + NAS同步 + 分集 + 质检
============================================================
  🌐 访问地址: http://127.0.0.1:8089/
  💾 数据库:   data/workbench.db
  📝 配置文件: backend/config.yaml
============================================================
```

浏览器自动打开 **http://localhost:8089** 🎉

---

## 🧩 界面预览

### 主页 Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│ 📅本月项目 │ 📁总项目 │ 🎬制作中 │ ✅质检通过 │ 🔍质检中 │ ⚠️缺集 │ 📦同步中 │
├──────────────────────────────────────────────────────────────────┤
│ 🔎 搜索  │ 🏢 部门  │ 🏷️ 月份  │ 📋 状态  │ ↕️ 排序: 状态 ▼   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ▼ 组内NAS                                                        │
│ ┌──────────────────────────────┐  ┌──────────────────────────────┐│
│ │ 🍭 与他的痛觉绑定             │  │ 👥 萌宝练气三万层            ││
│ │ [🎬剪辑中] 📅2026-08 [AI二部] │  │ [🔍审核中] 📅2026-08 [AI一部]││
│ │ ▓▓▓▓▓▓░░ 已输出 35/70        │  │ ▓▓▓░░░  已输出 0/70         ││
│ │ ⚠️ 缺第 3、5、8-12 集        │  │ ⚠️ 缺 70 集                 ││
│ │ [🔄] [📅] [📑分集] [📦同步]  │  │ [🔄] [📅] [📑分集] [📦同步] ││
│ └──────────────────────────────┘  └──────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 项目月份设置（下拉框 Modal）

```
┌──────────────────────────┐
│ 📅 设置项目月份           │
│ 她的游戏，我的棋局        │
│                          │
│ ┌────────────────────┐   │
│ │ — 清空（不统计）—  │   │
│ │ 2025-01            │   │
│ │ 2025-02            │   │
│ │ ...                │   │
│ │ 2026-08 · 本月 📌  │   │  ← 当前月自动高亮
│ │ 2026-09            │   │
│ │ ... 一直到 2027-12 │   │
│ └────────────────────┘   │
│           [取消] [确定]  │
└──────────────────────────┘
```

### 系统原生复制进度

点击批量回传 → 自动弹出 **Windows 系统资源管理器进度对话框**（`Shell.Application.CopyHere`），用户可见且可中断。批量操作共用一个合并后的 CopyHere 窗口。

---

## 🔌 API 接口

后端已注册 **38+ 个** JSON 路由。关键路由：

### 📁 项目管理

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `GET` | `/api/projects` | 分 section 的完整项目列表（名称去重） |
| `GET` | `/api/project_months` | **专门接口** — 返回 `{项目名: 'YYYY-MM'}` 月份映射（绕开 scan.py dict 缺失） |
| `POST` | `/api/project/<name>/update_month` | **设置月份**（传空字符串=清空不统计） |
| `POST` | `/api/scan` | 重新扫描磁盘 |
| `GET` | `/api/projects/light` | 轻量列表（分集 Tab 下拉） |
| `GET` | `/api/project/<name>` | 单个项目详情 |
| `GET` | `/api/project/<name>/episodes_status` | 实时扫描缺集 |
| `POST` | `/api/project/<name>/custom_status` | 更新项目状态 |
| `POST` | `/api/project/<name>/open_folder` | 用资源管理器打开 |
| `POST` | `/api/project/<name>/check_on_group` | 检查是否已在组盘 |

### 📑 分集

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `GET` | `/api/project/<name>/episodes_plan` | 分集计划 |
| `POST` | `/api/bulk/import_episodes` | 批量导入 |
| `GET` | `/api/fenji/suggest` | AI 分集建议 |
| `POST` | `/api/export_fenji` | 导出 Excel 模板 |

### 📦 同步 & 交付

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `POST` | `/api/sync/<name>` | robocopy 同步素材 |
| `GET` | `/api/sync/<name>/status` | 查询进度 |
| `POST` | `/api/deliver/<name>` | 单文件交付 |
| `POST` | `/api/deliver_batch/<name>` | **批量回传（Shell.Application 系统进度对话框）** |
| `POST` | `/api/deliver_compare/<name>` | 对比组内/制作部差异 |

### 👥 团队

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `GET` | `/api/team/members` | 列表 |
| `POST` | `/api/team/members` | 新增 |
| `PUT` | `/api/team/members/<id>` | 修改 |
| `DELETE` | `/api/team/members/<id>` | 删除 |

### 🎥 预览 & 🔍 质检

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `GET` | `/api/preview/<name>/<file>?mode=editing\|revising\|delivery` | 流式视频预览 |
| `POST` | `/api/qa/<name>/start` | 启动质检 |
| `GET` | `/api/qa/<name>/status` | 质检进度 |
| `GET` | `/api/qa/<name>/report` | 获取 HTML 报告 |

---

## 🗄️ 数据库

默认：`data/workbench.db`（SQLite，WAL 模式）

```sql
projects          -- 项目（name, source_path, group_path, production_path, total_episodes, 
                  --          custom_status, delivery_status, project_month, sync_status, ...）
team_members      -- 成员（name, title, department, episode_count）
episode_plans     -- 分集（project_name, episode_num, editor）
qa_records        -- 质检（project_name, status, score, report_path）
sync_log          -- 同步日志
delivery_records  -- 交付记录
```

**`project_month` 字段说明**：`TEXT` 类型，格式 `YYYY-MM`。为空或 NULL 表示该项目不参与月份统计。空壳项目（无状态 + 未交付 + 0 集）即使有月份也被前端 UI 过滤掉。

---

## 🧪 开发指南

### 调试模式启动后端

```bash
cd backend
python -c "from app import create_app; create_app().run(debug=True, port=8089)"
```

### 新增路由

```python
# 在 backend/app.py 或 enhanced_routes.py 中
from app import db
from scan import ScanMixin

@app.route('/api/my_feature')
def my_feature():
    projects = db.get_all_projects()
    return jsonify(ok=True, data=projects)
```

### 新增前端 JS 模块

在 `static/js/` 下新建文件，在 `templates/index.html` 底部 `<script>` 引入（顺序依赖注意）。已暴露的全局变量：

| 变量 | 类型 | 来源 |
|------|------|------|
| `projects` | `Array` | project.js — 去重后的 flat 列表 |
| `allSections` | `Array` | project.js — 分 section 原始数据 |
| `allProjects` | `Object` | project.js — `{production, group_all, group_completed}` |
| `api()` | `Function` | 全局 — fetch 封装，统一鉴权 |
| `toast()` | `Function` | 全局 — 轻提示 |
| `renderDashboard()` | `Function` | core.js — 重绘卡片 |
| `loadProjects()` | `Function` | project.js — 重新拉取 |

### 扩展 NAS 路径

修改 `backend/config.yaml` → `nas.production_roots`，然后在 `scan.py` 扫描逻辑中处理新目录层级。

---

## 🐛 常见问题

<details>
<summary><b>启动后页面空白？</b></summary>

检查 `backend/config.yaml` 里的 `nas.production_roots` 和 `nas.group_root` 是否存在且可访问。脚本只显示路径可达的项目。
</details>

<details>
<summary><b>视频预览"无法加载"？</b></summary>

后端 `get_file_path_for_preview()` 已合并 `source`/`auto`/`editing` 三种模式的处理。常见原因：
1. 成片目录还没输出视频 → 先手动点卡片上的 🔄 刷新
2. N/O 盘网络断开 → 检查 UNC 路径可达性
3. 前端 mode 值不匹配 → 剪辑中项目默认用 `editing` 模式
</details>

<details>
<summary><b>项目月份刷新后丢失？</b></summary>

已通过三重保障解决：
1. 后端 `/api/project_months` 专门接口直接 SELECT
2. 浏览器 localStorage `wb_project_months` 缓存
3. 前端内存 merge 时跳过 scan.py dict 缺失问题

如果还是丢失，在浏览器控制台跑 `localStorage.removeItem('wb_project_months')` 然后强刷。
</details>

<details>
<summary><b>批量回传进度在哪里？</b></summary>

点击"批量回传"后会弹出 **Windows 系统资源管理器进度对话框**（蓝色复制进度条）。这是 `Shell.Application.CopyHere` 的原生效果，用户可见且可中断。批量操作通过临时目录硬链接合并，共用一个 CopyHere 窗口。
</details>

<details>
<summary><b>数据库越来越大？</b></summary>

日志自动轮转（10MB × 5 份）。SQLite 的 WAL 文件（`workbench.db-wal`）正常关闭后会自动合并。
</details>

<details>
<summary><b>重置为干净状态？</b></summary>

```bash
del data\workbench.db data\workbench.db-shm data\workbench.db-wal
python main.py    # 重启后自动重建表结构
```
</details>

---

## 📜 依赖 & 日志

### Python 依赖

| 包 | 版本 | 用途 |
|:---|:---|:---|
| flask | ≥ 2.0 | Web 框架 |
| waitress | ≥ 2.1 | WSGI 生产服务器（无则回退 Flask app.run） |
| watchdog | ≥ 3.0 | Watchdog 目录监听 |
| PyYAML | ≥ 6.0 | config.yaml 加载 |
| openpyxl | ≥ 3.0 | Excel 模板导出 |
| numpy | ≥ 1.20 | 数值计算（PSNR/SSIM） |
| opencv-python | ≥ 4.5 | 视频质检（黑帧/花屏检测） |
| Pillow | ≥ 8.0 | 图像处理 |

Python 3.10+ 标准库：`subprocess`（robocopy）· `sqlite3` · `threading`（watcher）· `pathlib` · `shutil`（Shell.Application 通过 wscript 调用）

### 第三方组件致谢

<div align="center">

[![Flask](https://img.shields.io/badge/Flask-000000?style=flat&logo=flask)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=flat&logo=opencv)](https://opencv.org/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat&logo=sqlite)](https://www.sqlite.org/)

</div>

---

## 🗺️ 路线图

- [x] **v2.0** — 全流程状态机 + 分集面板 + 视频质检 + Watchdog
- [x] **v2.1** — 项目月份统计 + 下拉框选择 + Shell.Application 系统原生复制 + 批量回传共用进度窗口 + 按名称去重统计 + 成片/修改/交付三场景一键打开资源管理器
- [ ] **v2.2** — Premiere Pro CEP 插件联动（字幕自动导入）
- [ ] **v2.3** — 多人实时协作（WebSocket 推送状态变更）
- [ ] **v2.4** — 移动端适配（响应式 Dashboard）

---

## 📄 License

Released under the [MIT License](LICENSE)

<div align="center">

**Made with ❤️ by vhdaqd0410**

[⬆️ Back to top](#-视频工作台)

</div>
