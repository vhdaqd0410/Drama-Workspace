<div align="center">

# 🎬 视频工作台

### AI 漫剧生产流程一站式管理平台

[![Python](https://img.shields.io/badge/python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.5+-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/status-active-brightgreen?style=for-the-badge)]()
[![Version](https://img.shields.io/badge/v2.6.0-blue?style=for-the-badge)]()

📡 **实时扫描 · 可视化进度 · 智能协作 · 一键交付 · 快捷键直达**

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
        <h3>⌨️</h3>
        <b>全局快捷键</b><br/>任意程序唤起搜索
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
- [⌨️ 快捷键](#️-快捷键)
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
| 📊 分集管理 | Chips 可视化分配 · 批量粘贴 · 自动均分 · 人员模板 · 历史复用 |
| 📥 Excel 分集同步 | 上传分集 Excel 自动同步到项目，解决已完成项目未设分集导致工作量不准 |
| 📈 进度扫描 | 自动扫描 `01上映单集版` 目录，缺集红色高亮 + 实时百分比 |
| ✂️ 剪辑完成提醒 | 剪辑中项目达到设定集数自动弹出"进入审核"提醒 |
| 📊 数据看板 | 剪辑师工作量 · 部门统计 · 产能趋势（近6月），月度报告整合 |
| 🎥 成片预览 | editing/revising/delivery 三模式 · 跨盘 fallback · 倍速播放 · 步进 |
| 💻 系统原生复制 | **Shell.Application.CopyHere** 弹系统资源管理器进度对话框，用户可见 |
| 📦 素材/成片回传 | 批量回传真实进度追踪 · 完成弹窗（打开目录/复制路径） |
| 📅 项目月份 | 下拉框选择月份 · 后端持久化 · 按名称去重统计 |
| 🔍 视频质检 | OpenCV 黑帧检测 · 花屏检测 · PSNR/SSIM · 批量质检报告 |
| ⌨️ 全局快捷键 | 全局搜索/唤醒热键（系统级，任意程序可用）· 可录制自定义 |
| 👥 团队管理 | 成员 CRUD · 职位下拉 · 部门归属 · 集数自动移位 |
| 👀 Watchdog | 后台线程监听成片目录 · 稳定 30s 后自动标记 |
| 📑 Excel 导出 | 分集分配一键导出模板 · 自动备份 · 追加写入不覆盖 |
| 🏢 NAS 路径设置 | 设置界面可自定义/编辑组内与制作部路径，含可访问性检测 |

---

## 🏗️ 系统架构

### 后端模块拆分（Mixin 继承）

```
app.py ─┬── scan.py      (ScanMixin)      — get_projects_enriched, 自动发现项目
        ├── sync.py      (SyncMixin)      — robocopy + Shell.Application.CopyHere
        ├── deliver.py   (DeliverMixin)   — 成片/修改/交付三场景回传 + 进度追踪
        └── preview.py   (PreviewMixin)   — 视频路径解析 + 流式预览路由

enhanced_routes.py   — 扩展路由（团队、分集、Excel同步、质检、设置）
bulk_api.py          — 批量操作 + 任务中心 + 月度报告 + 数据看板
fenji.py / fenji_exporter.py — 分集分配 + Excel 导出
qa_engine.py + detection.py — 质检引擎（黑帧/花屏/PSNR/SSIM）
watcher.py           — Watchdog 后台线程
db.py                — SQLite ORM + 建表迁移 + 用户设置(key-value)
utils.py             — 共享工具函数
main_desktop.py      — 桌面版入口（托盘 + 全局热键 RegisterHotKey）
```

### 前端模块拆分

```
templates/index.html ── 骨架 HTML + 内联样式（1028 行）

static/js/
├── core.js              (1064 行) — Dashboard 渲染 / 数据看板 / 快捷键 / 剪辑提醒
├── project.js           (234 行)  — 项目加载 / 月份 merge / 名称去重
├── episode.js           (598 行)  — 分集详情 / 缺集扫描 / setProjectMonth
├── fenji-assign.js      (1184 行) — 分集分配 / 人员模板 / Excel同步
├── fenji-init.js        (51 行)   — 分集初始化
├── deliverables.js      (329 行)  — 成片/修改预览面板
├── deliver-batch.js     (212 行)  — 批量回传进度
├── deliver-events.js    (373 行)  — 回传事件 + 完成弹窗
├── preview.js           (122 行)  — 视频预览弹窗
├── team.js              (448 行)  — 团队成员 + 设置 + NAS路径管理 + 快捷键录制
├── qa.js                (1087 行) — 质检中心 + 批量质检
├── tabs.js              (246 行)  — 月度报告 / 任务中心
└── app.js               (67 行)   — 应用初始化 + SSE + 定时任务
```

### 数据流向

```
┌─────────────────────────────────────────────────────────────┐
│ 浏览器 (桌面版 WebView / 网页)                              │
│  index.html → 14 个 JS 模块（core / project / episode / ...）│
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/JSON + SSE(实时推送)
┌────────────────────▼────────────────────────────────────────┐
│ Flask 后端 0.0.0.0:8089  (waitress WSGI 生产模式)          │
│                                                             │
│  app.py (1207行)                                            │
│  ├── /api/projects            → ScanMixin.get_projects     │
│  ├── /api/project_months      → SELECT project_month 专门接口│
│  ├── /api/project/<n>/update_month  → 月份下拉框持久化       │
│  ├── /api/project/<n>/episodes_status → 实时缺集扫描         │
│  ├── /api/preview/<n>/<f>     → PreviewMixin 流式视频       │
│  ├── /api/stats/dashboard     → 数据看板(剪辑师/部门/趋势)  │
│  ├── /api/fenji/sync_from_excel → Excel分集同步到项目        │
│  ├── /api/settings            → 用户设置持久化(key-value)   │
│  └── 70+ 其他路由                                            │
│                                                             │
│  enhanced_routes.py  bulk_api.py  fenji.py  qa_engine.py    │
│  main_desktop.py — 托盘 + 全局热键(RegisterHotKey)          │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│ 存储层                                                       │
│                                                             │
│ 💾 SQLite (data/workbench.db)                               │
│   projects / team_members / qa_runs / qa_results /         │
│   sync_logs / delivery_logs / deliver_runs / app_settings   │
│                                                             │
│ 📁 NAS 磁盘                                                  │
│   N:\ 制作部 (多部门)    O:\ 组内NAS (剪辑一组)               │
│                                                             │
│ 🧠 浏览器 localStorage + 后端 app_settings 双重持久化        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 项目结构

```
Drama-Workspace/
│
├── 🚀 main.py                     # 统一启动入口（自动打开浏览器）
├── 🚀 main_desktop.py             # 桌面版入口（WebView + 托盘 + 全局热键）
├── 🛠️ start.bat / start.vbs       # Windows 一键启动
├── 🛠️ start_desktop.vbs           # 桌面版无黑窗启动
├── 📦 requirements.txt            # Python 依赖清单
├── 🔒 .gitignore                  # 排除 DB / 日志 / config.yaml / 临时脚本
├── 📖 README.md                   # 项目文档（本文件）
│
├── 🐍 backend/                    # ═══════ Python 后端 ═══════
│   ├── __init__.py                # 包初始化：导出 create_app / db
│   ├── app.py                     # Flask 主入口 + 核心路由（1207 行）
│   ├── enhanced_routes.py         # 扩展路由：团队/分集/Excel同步/质检/设置（1195 行）
│   ├── bulk_api.py                # 批量操作/任务中心/月度报告/数据看板（369 行）
│   ├── scan.py ⭐ Mixin           # 项目扫描 + 按名称去重（481 行）
│   ├── sync.py ⭐ Mixin           # robocopy + Shell.Application.CopyHere（597 行）
│   ├── deliver.py ⭐ Mixin        # 成片/修改/交付 三场景回传 + 进度追踪（2081 行）
│   ├── preview.py ⭐ Mixin        # 视频路径解析 + 跨盘 fallback（333 行）
│   ├── sync_engine.py             # 兼容桥：从 app 导入 Mixin + 缓存持久化
│   ├── db.py                      # SQLite ORM + 建表 + 用户设置（704 行）
│   ├── fenji.py                   # 分集分配逻辑（83 行）
│   ├── fenji_exporter.py          # Excel 模板导出 + 追加写入（156 行）
│   ├── qa_engine.py               # 视频质检引擎（940 行）
│   ├── detection.py               # OpenCV 黑帧/花屏/PSNR/SSIM（1244 行）
│   ├── watcher.py                 # Watchdog 后台线程（234 行）
│   ├── version.py                 # ⭐ 统一版本号来源（VERSION / APP_TITLE）
│   ├── config.py                  # (废弃) 旧 JSON 配置模块，已由 config.yaml 取代
│   ├── config.example.yaml        # 📋 配置模板（公开，不含真实路径）
│   ├── config.yaml                # ⚠️ 唯一配置源（已加入 .gitignore，含 NAS/服务/质检路径）
│   ├── utils.py                   # 共享工具函数
│   └── report_template.py         # 质检报告 HTML 模板
│
├── 🖥️ templates/
│   └── index.html                 # 单页应用骨架（1028 行 · 样式内联）
│
├── 🧩 static/js/                  # ═══════ 前端模块化 ═══════
│   ├── core.js                    # Dashboard / 数据看板 / 快捷键 / 剪辑提醒
│   ├── project.js                 # 项目加载 / 名称去重 / localStorage merge
│   ├── episode.js                 # 缺集扫描 / setProjectMonth 下拉框
│   ├── fenji-assign.js            # Chips 可视化分配 / 人员模板 / Excel同步
│   ├── fenji-init.js              # 分集初始化
│   ├── deliverables.js            # 成片/修改预览
│   ├── deliver-batch.js           # 批量回传进度
│   ├── deliver-events.js          # 回传事件 / 完成弹窗
│   ├── preview.js                 # 视频预览弹窗
│   ├── team.js                    # 团队成员 / 设置 / NAS路径 / 快捷键录制
│   ├── qa.js                      # 质检中心 / 批量质检
│   ├── tabs.js                    # 月度报告 / 任务中心
│   └── app.js                     # 应用初始化 + SSE + 定时任务
│
└── 💾 data/                       # ═══════ 运行时数据（自动生成）═══════
    ├── workbench.db               # SQLite 数据库
    ├── output_dirs_cache.json     # 上映单集版目录缓存（持久化）
    ├── fenji_templates/           # 分集导出模板
    ├── fenji_targets/             # 分集累积目标文件
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
  🎬 视频工作台 v2.6.0
  📦 统一集成: 项目管理 + NAS同步 + 分集 + 质检 + 数据看板
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
│ 📁总项目 │ 📅本月项目 │ ✅本月已完成 │ 🎬制作中 │                   │
├──────────────────────────────────────────────────────────────────┤
│ 🔎 搜索  │ 🏢 部门  │ 🏷️ 月份  │ 📋 状态  │ ↕️ 排序: 状态 ▼   │
├──────────────────────────────────────────────────────────────────┤
│ ┌─ 概览图：部门项目分布(本月) ─┐ ┌─ 工作流状态分布(本月) ──────┐ │
│ └────────────────────────────┘ └────────────────────────────┘ │
│                                                                  │
│ ▼ 组内NAS                                                        │
│ ┌──────────────────────────────┐  ┌──────────────────────────────┐│
│ │ 🍭 与他的痛觉绑定             │  │ 👥 萌宝练气三万层            ││
│ │ [🎬剪辑中] 📅2026-08 [AI二部] │  │ [🔍审核中] 📅2026-08 [AI一部]││
│ │ ▓▓▓▓▓▓░░ 已输出 35/70        │  │ (审核中/修改中不显示进度)    ││
│ │ ⚠️ 缺第 3、5、8-12 集        │  │                              ││
│ │ [🔄] [📑分集] [✏️标记修改]  │  │ [🔄] [📑分集] [✏️标记修改]  ││
│ └──────────────────────────────┘  └──────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 全局搜索框（快捷键唤起）

```
┌──────────────────────────────────────────────────────┐
│ 🔍 [搜索项目名称、月份、拼音首字母...]      Ctrl+Space│
│ ──────────────────────────────────────────────────── │
│  (模糊搜索结果，点击定位到项目卡片 + 高亮动画)        │
│  ↑↓ 选择 · Enter 打开 · Esc 关闭                     │
└──────────────────────────────────────────────────────┘
```

### 数据看板（月度报告 Tab）

```
┌─ 👥 剪辑师工作量(本月) ──┐ ┌─ 🏢 部门项目统计 ──────┐
│ 金文龙 ▓▓▓▓▓▓ 108集 17项目│ │ AI二部 ▓▓▓▓▓▓ 8项目 5完成│
│ 袁绍杰 ▓▓▓▓▓▓ 106集 17项目│ │ AI一部 ▓▓▓▓░░ 7项目 3完成│
│ ...                       │ │ ...                    │
└───────────────────────────┘ └────────────────────────┘
┌─ 📈 产能趋势(近6月) ─────────────────────────────────┐
│ ▓▓▓ 立项  ▓▓▓ 完成  ▓▓▓ 交付                        │
└─────────────────────────────────────────────────────┘
```

### 系统原生复制进度

点击批量回传 → 自动弹出 **Windows 系统资源管理器进度对话框**（`Shell.Application.CopyHere`），用户可见且可中断。批量操作共用一个合并后的 CopyHere 窗口。回传完成后弹出"打开回传目录 / 复制路径"窗口。

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
| `POST` | `/api/fenji/sync_from_excel` | **解析分集 Excel 同步到项目（工作量统计）** |
| `GET` | `/api/fenji/person_templates` | 人员模板列表 |
| `POST` | `/api/fenji/person_templates` | 保存人员模板 |
| `DELETE` | `/api/fenji/person_templates` | 删除人员模板 |
| `GET` | `/api/fenji/templates` | 导出模板列表 |
| `POST` | `/api/fenji/upload_template` | 上传导出模板 |
| `GET` | `/api/fenji/targets` | 累积目标文件列表 |
| `POST` | `/api/fenji/upload_target` | 上传目标文件 |

### 📦 同步 & 交付

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `POST` | `/api/sync/<name>` | robocopy 同步素材 |
| `GET` | `/api/sync/<name>/status` | 查询进度 |
| `POST` | `/api/deliver/<name>` | 单文件交付 |
| `POST` | `/api/deliver_batch/<name>` | **批量回传（Shell.Application 系统进度对话框）** |
| `POST` | `/api/deliver_folder/<name>` | 文件夹/整目录回传 |
| `GET` | `/api/project/<name>/deliver_dst` | 获取回传目标目录（完成弹窗用） |

### 📊 数据看板 & 设置

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `GET` | `/api/stats/dashboard` | **数据看板（剪辑师工作量/部门/趋势）** |
| `GET` | `/api/report/monthly` | 月度报告 |
| `GET` | `/api/report/monthly/export` | 月度报告 Excel 导出 |
| `GET` | `/api/activity_log` | 活动日志 |
| `GET` | `/api/settings` | 用户设置（key-value） |
| `PUT` | `/api/settings` | 保存用户设置 |
| `GET` | `/api/config/paths` | NAS 路径配置 |
| `POST` | `/api/config/paths` | 新增/更新 NAS 路径 |
| `DELETE` | `/api/config/paths` | 删除 NAS 路径 |
| `POST` | `/api/config/path_check` | **NAS 路径可访问性检测** |

### 🔍 质检

| 方法 | 路径 | 说明 |
|:---:|:---|:---|
| `POST` | `/api/project/<name>/qa_start` | 启动质检（自动设质检中） |
| `GET` | `/api/project/<name>/qa_status` | 质检进度 |
| `GET` | `/api/project/<name>/qa_report` | HTML 报告 |
| `GET` | `/api/qa/summary` | **质检统计概览** |
| `POST` | `/api/qa/batch_start` | **批量启动质检** |
| `GET` | `/api/qa/batch_report` | **批量质检汇总报告** |

---

## 🗄️ 数据库

默认：`data/workbench.db`（SQLite，WAL 模式）

```sql
projects          -- 项目（name, group_path, production_path, custom_status,
                  --          delivery_status, total_episodes, episode_plan, project_month, ...）
team_members      -- 成员（name, role, title, department, skills）
qa_runs           -- 质检批次（project_name, status, total, passed, failed, ...）
qa_results        -- 质检明细（qa_run_id, video_name, version, status, ...）
sync_logs         -- 同步日志
delivery_logs     -- 交付记录
deliver_runs      -- 交付批次（src, dst, total_files, status, ...）
app_settings      -- 用户设置（key-value：模板选择/目标路径/快捷键/人员模板等）
```

**`project_month` 字段说明**：`TEXT` 类型，格式 `YYYY-MM`。为空或 NULL 表示该项目不参与月份统计。空壳项目（无状态 + 未交付 + 0 集）即使有月份也被前端 UI 过滤掉。

---

## ⌨️ 快捷键

三组快捷键都可在**设置界面**录制自定义（点"🎹 录制"后按任意组合键，如 Ctrl+Alt+Z、Alt+1、Ctrl+Shift+F5）。

| 快捷键 | 作用 | 默认 |
|:---|:---|:---|
| 🌐 全局搜索项目 | **系统级热键**，软件在后台/任意程序都可唤起搜索框 | Ctrl+Alt+S |
| 📄 页面内搜索 | 软件窗口内弹出搜索框 | Ctrl+Space |
| 🪟 全局唤醒窗口 | **系统级热键**，从托盘/后台唤回窗口 | Ctrl+Shift+B |

**说明**：
- 全局搜索/唤醒用 Windows `RegisterHotKey` 注册，**任意程序下可用**
- 全局搜索按下列**唤起窗口 + 弹出搜索框**（通过 SSE 通知前端）
- 页面内搜索支持模糊匹配（子串 + 子序列）
- 搜索点击结果 → 定位到项目卡片 + 高亮动画
- ⚠️ 全局热键修改后需**重启软件**生效

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

**推荐方式**：在**设置界面 → NAS路径**直接管理（组内/制作部路径列表、添加/删除/可访问性检测），自动写回 `config.yaml` 并重载。

**手动方式**：修改 `backend/config.yaml` → `nas.production_roots` / `nas.group_root`，然后在 `scan.py` 扫描逻辑中处理新目录层级。

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

点击"批量回传"后会弹出 **Windows 系统资源管理器进度对话框**（蓝色复制进度条）。这是 `Shell.Application.CopyHere` 的原生效果。后端会**轮询目标目录实时更新进度**，前端进度条显示真实百分比。回传完成后弹出"打开回传目录 / 复制路径"窗口。
</details>

<details>
<summary><b>剪辑师工作量统计不准确？</b></summary>

工作量基于项目的 `episode_plan`（分集 plan）。如果之前已完成的项目在软件里没设分集，会导致统计不准。解决：
1. 到**分集管理 → 📥 从Excel同步**上传分集表格
2. 系统自动解析并同步到项目，工作量即更新
</details>

<details>
<summary><b>全局搜索/唤醒快捷键不生效？</b></summary>

1. 全局热键在**软件启动时注册**，修改后需**重启软件**
2. 如果注册失败（被其他程序占用），启动日志会提示，可换一个组合
3. 页面内搜索快捷键修改后**立即生效**（F5 刷新页面）
</details>

<details>
<summary><b>剪辑完成不提醒？</b></summary>

系统每3分钟自动扫描"剪辑中"项目，达到设定集数（`当前集数 ≥ 总集数`）才提醒。如果项目没设总集数（`total_episodes` 为0），不会触发提醒。请先在分集管理中设置总集数。
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
- [x] **v2.2** — 性能优化（目录缓存持久化、日志治理、Watchdog 启用）+ 交付完整性检测
- [x] **v2.3** — 异常监控 + 质检工作流自动流转 + 质检统计 + 批量质检
- [x] **v2.4** — 分集管理持久化（模板/目标文件/历史记录）+ 人员模板 + 快捷键录制自定义
- [x] **v2.5** — 全局搜索/唤醒系统热键（RegisterHotKey）+ 搜索定位卡片动画 + 回传进度与完成反馈
- [x] **v2.6** — 工作量/数据看板 + Excel 分集同步 + 剪辑完成自动提醒 + NAS 路径自定义
- [ ] **v2.7** — Premiere Pro CEP 插件联动（字幕自动导入）
- [ ] **v2.8** — 多人实时协作（WebSocket 推送状态变更）
- [ ] **v2.9** — 移动端适配（响应式 Dashboard）

---

## 📄 License

Released under the [MIT License](LICENSE)

<div align="center">

**Made with ❤️ by vhdaqd0410**

[⬆️ Back to top](#-视频工作台)

</div>
