# 视频工作台 · 开发与口径说明（CONTEXT.md）

> 当前版本 **v3.4.0**（`backend/version.py` 单一来源）。README 的路线图/文件清单/版本徽章应与之保持一致；
> 若某文件新增/删除/改名，请同步更新 README「项目结构」与本文档「后端路由清单」。

本文件是给开发者/后续维护用的**单一事实来源**：说明架构、关键数据口径、路由约定与代码导航，
避免后续改动再次出现"口径不一致"或"不知道数据从哪来"的问题。

> 维护规则：凡修改任何"统计/指标/口径"相关的代码，必须同步更新本文件对应小节。

---

## 1. 技术栈与运行方式

- **后端**：Python 3 / Flask + waitress，SQLite（WAL）数据库 `data/workbench.db`。
- **前端**：原生 JavaScript SPA（无框架），单页模板 `templates/index.html`，脚本在 `static/js/`。
- **桌面端**：pywebview 外壳（`main_desktop.py`）+ 系统托盘 pystray；浏览器也可访问。
- **NAS 集成**：扫描 O 盘/组盘目录发现项目；`config.yaml` 是唯一配置源。
- **鉴权**：`_auth_gate` 需要 `X-API-KEY` 请求头或 `?key=`；`_PUBLIC_PREFIXES` 放行白名单（如 `/api/thumbnail`）。

---

## 2. 数据库表（`data/workbench.db`）

| 表 | 说明 | 关键字段 |
|---|---|---|
| `projects` | 项目主表 | `name`(唯一), `department`, `project_month`(动态列), `custom_status`, `delivery_status`, `total_episodes`, `current_episodes`, `episode_plan`(JSON: `{集数:剪辑师}`), `delivered_date`(YYYY-MM-DD), `production_path`, `group_path` |
| `project_todos` | 项目待办 | `project_name`, `text`, `done`, `priority`, `created_at` |
| `audit_logs` | 审计/时间轴 | `project_name`, `action`, `detail`, `created_at` |
| `sync_logs` | NAS 同步日志 | `project_name`, `status`, ... |
| `delivery_logs` | 成片回传日志 | `project_name`, `file_size`, `status`, `created_at` |
| `qa_runs` / `qa_runs_items` | 质检记录 | ... |

> 注意：`project_month`、`delivered_date` 等是通过 `ALTER TABLE ADD COLUMN` 迁移追加的动态列；
> 修改 `projects` 结构时先确认是否已在 `db.py` 的迁移逻辑里。

---

## 3. 核心统计口径（务必统一，勿各写一套）

| 指标 | 定义 | 权威来源 |
|---|---|---|
| **总项目数** | 有制作痕迹的项目（去重） | `scan.compute_overview_stats().total` |
| **本月项目 / 当月项目数** | `project_month == 当前 YYYY-MM` 且有制作痕迹 | `compute_overview_stats().this_month` |
| **本月已完成 / 当月已完成** | 上述本月项目里 `custom_status == '已完成'` | `compute_overview_stats().this_month_done` |
| **制作中 / 进行中** | 上述本月项目里 `custom_status` 非空且非 '已完成' | `compute_overview_stats().producing` |
| **恒等式** | `本月项目 = 本月已完成 + 制作中`（必成立） | `compute_overview_stats` 内部校验 |
| **各剪辑集数（剪辑师工作量）** | 从项目 `episode_plan`（分集数据，最终口径）逐集计数到对应剪辑师，按 `project_month` 过滤当月 | `features.aggregate_editor_workload()`（三端点同源） |
| **当月状态分布** | 前端 `projects` 数组按 `project_month == 当前月` 过滤后统计 `custom_status` | 首页 `renderOverviewCharts` |
| **交付日期** | `projects.delivered_date`（YYYY-MM-DD），非空即计入交付日历该日 | `/api/insights/calendar` |
| **月度报告项目清单** | DB `projects` 按 `project_month == 所选月份` | `/api/report/monthly` |
| **回传数据量** | `delivery_logs` 按当月 `created_at` + `status='success'` | `/api/report/monthly` 的 `delivery_stats` |

### 关键约定
- **"当月"一律指 `project_month`，不是 `created_at`**。`created_at` 是记录创建时间，不能当业务月份用。
- **前端统一用 `window._overviewStats`（来自 `/api/projects` 的 `overview_stats`）** 显示首页/洞察的 KPI，避免各端口径漂移。
- **各剪辑集数统一用 `features.aggregate_editor_workload(db, month=...)`**（数据洞察 `/api/insights/summary`、数据看板 `/api/stats/dashboard`、月度报告同源）。统计口径始终以分集数据(`episode_plan`)为最终数据源；`editor_workload` 列仅向下兼容、不被统计读取。
- **数据洞察 KPI 用 `features.compute_insights_summary(db, month)`**：本月项目=有制作痕迹且 `project_month==当月`；本月已完成=其中 `custom_status=='已完成'`（**不是 `delivered_date`**）；制作中=其中状态非空非已完成。
- **分集解析统一用 `fenji_parser.parse_assign_line()`**（features / enhanced_routes / fenji 三处共用，避免正则漂移）。

---

## 4. 关键路由清单

### 数据洞察 / 交付日历（`backend/features.py`）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/insights/summary` | 洞察汇总（含 monthProjectCount/monthCompleted/inProgress/statusMap/editorEpisodes/memberCount） |
| GET | `/api/insights/calendar?month=YYYY-MM` | 交付日历 `{days:{YYYY-MM-DD:[项目名]}}` |
| POST | `/api/project/<name>/delivered_date` | 设置/清除项目交付日期 `{date:'YYYY-MM-DD' or ''}` |
| POST | `/api/insights/sync_delivery_dates` | 从分集目标表格读胶片日期，更新 `delivered_date` |
| GET | `/api/insights/export?save=1` | 导出项目档案 CSV；`save=1` 时保存到 `data/exports/` 并返回路径 |
| POST | `/api/insights/export/open_folder` | 用资源管理器打开导出目录 |

### 待办（`backend/features.py`）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/project/<name>/todos` | 查询/新增待办 |
| PUT/DELETE | `/api/project/<name>/todos/<id>` | 更新(勾选)/删除待办 |

### 项目 / 统计 / 报告（`backend/bulk_api.py`, `enhanced_routes.py`）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects` | 富集项目列表 + `overview_stats` |
| GET | `/api/stats/dashboard` | 剪辑师工作量 / 部门统计 / 产能趋势(近6月) |
| GET | `/api/report/monthly?month=` | 月度报告；`/export` 下载 Excel |
| GET | `/api/project/<name>` | 项目详情 |

---

## 5. 交付日期联动逻辑（重要）

- 项目 `custom_status` 改为 **"已完成"** 时（`deliver.set_custom_status`），若尚无 `delivered_date`，自动写为当天日期。
- 分集管理导出到目标表格后（`export_excel` 写目标文件成功），**后台线程自动**调用 `features.sync_delivery_dates_from_target()` 读取胶片日期更新 `delivered_date`。
- 因此交付日历会随"状态改已完成 / 分集导出"自动更新，无需手工同步。

---

## 6. 前端导航

- **页签**（`switchTab(name)`）：`dashboard`(首页) / `fenji`(分集) / `qa`(质检) / `activity`(动态) / `report`(月度报告) / `editor`(剪辑师) / `nameplate`(人名条) / `settings`(设置)。
- **全局命名空间**：`static/js/wb-shared.js`（`window.WB` 命名空间，最先加载；含**统一转义 `WB.escHtml`**，全站禁止再各自定义 escHtml/htm/jsq，避免三处定义不一致）。`static/js/wb-features.js`（剪辑师视图 `WB.editor` / 离线只读 `WB.offline`）、`static/js/wb-mobile.js`（手机端专属界面）。
- **分集解析统一**：`static/js/fenji-core.js`（`FenjiCore` 分集工具/去重）+ 后端 `backend/fenji_parser.py`（`parse_assign_line` 三处共用，避免正则漂移）。
- **新增后端接口**：`backend/schedule_api.py` 提供 `/api/editor/view`(剪辑师聚合)、`/api/offline/cache`(离线缓存打包)；`/api/projects/episodes_status_batch`(批量集数进度，N+1 优化，在 enhanced_routes.py)；`/api/insights/*` 与 `/api/commission/*`（数据洞察/交付日历/提成绩效，见 backend/features.py、commission.py）。
- **新增 DB 列**：`projects.output_dir_name`(成片目录项目级覆盖)、`projects.delivery_folder`(交付目录项目级覆盖)。
- **集号识别单源**：`backend/episode_number.py` 是集号提取正则与逻辑的唯一来源，`deliver.py` 与 `preview.py` 均通过 `self._extract_episode_number` 委托它，避免正则漂移。
- **CEP 插件联动**：`plugins/premiere-cep/` 是 Premiere Pro CEP 插件（读取项目/标记剪辑完成/更新集数）。后端为支持它：`/api/*` 已开放 CORS（`Access-Control-Allow-Origin:*` + OPTIONS 预检，仍走 X-API-KEY 鉴权）；新增 `POST /api/project/<name>/set_episodes`（更新 current/total_episodes，供外部工具调用）。
- **目录名统一解析**：`backend/output_dir_util.py` 是成片输出目录名 / 交付目录名的唯一解析源，`sync.py` 与 `watcher.py` 均调用它，避免重复漂移。
- **本地剪辑项目**：`backend/local_project.py` 提供 `create_local_project()`，根据分集分配(`episode_plan`)确定"我"(设置项 `my_editor_name`)负责的集数，在本地项目盘(设置项 `local_project_root`)创建「序号-项目名」文件夹(序号用 `_next_seq` 递增)，复制模板结构(设置项 `local_project_template`)，并**只拉取负责集**的素材(扁平复制到 `01原素材/第N集 剪辑师名/`)。接口 `POST /api/project/<name>/create_local_project` 为异步(后台线程)，进度经 `GET /api/project/<name>/local_project_progress` 轮询。集号识别 `_extract_episode_number` 会**排除结构目录序号**(`NN_结构词` 如 `01_抽卡素材` 不算集号)，避免误拉全部素材。
- **制作部自动扫描**：`backend/project_scan_service.py` 提供 `start_scheduler()`，daemon 线程每 10 分钟调用 `scan_projects()` 自动发现制作部新建项目(幂等 upsert)，在 app.py 启动时注册。`scan.py` 的 `_looks_like_project` 已修复：编号正则放宽为任意位置 4-6 位数字，且 `_CATEGORY_WORDS` 移除"海外/国内"(避免误伤含"国内版/海外版"的项目名)。
- **手机远程访问**：后端 `web.host` 已改为 `0.0.0.0`（`backend/config.yaml`），`main_desktop.py` 的 `_run_server` 也从 config 读取 host（默认 0.0.0.0）。通过 **Tailscale 组网**访问（电脑 `100.68.53.62`），不暴露公网。API key 由后端在渲染 `index.html` 时自动注入 `window.__API_KEY__`，手机端无需处理。安卓 WebView 壳 App 源码在 `mobile-app/WorkbenchMobile/`。

## 7. 隐私与 .gitignore

- 真实业务数据（`data/workbench.db`、`data/backups/`、`data/thumbs/`、`data/exports/`、`data/fenji_targets/`、插件数据/输出）均已在 `.gitignore`，**不得提交**。
- 提交前用 `git status` 确认没有把运行时产物打进仓库。
