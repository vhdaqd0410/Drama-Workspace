# 视频工作台 · 下一步开发计划（ROADMAP）

> 基于 2026-08 代码评审 + 多轮持续推进。已完成的见下方「已完成」。
> 优先级：P0=崩溃/数据错误/安全；P1=重要改进；P2=长期技术债。

## 一、已完成
### 第一轮（代码评审后）
- P0 三统计端点统一口径（compute_insights_summary），修 monthCompleted 误用 delivered_date
- P0 统一分集解析器（fenji_parser.py），消除三处重复漂移
- P0 前端 onclick XSS（jsq 统一转义，28 处）+ 统一 escHtml 到 WB.escHtml
- P0 产能趋势 1~5 月崩溃（backfill_months）
- P1 限制任意路径写文件 / 删除死代码 / except 补日志 / CONTEXT.md 口径同步
- 测试 39→49

### 第二轮（运行健壮性修复）
- P0 QA 引擎 hardsub_folders=None 遍历崩溃（qa_engine + enhanced_routes 兜底）
- P0 待办 priority 传入中文/垃圾导致 int() 崩溃（db._coerce_priority 统一规范化）
- P0 分集 Excel 目标文件被占用写失败（写前占用检测 + 409 中文提示）
- P0 目录缓存写盘节流失效 + WinError 5（sync.py 更新 _last_cache_save_size + 重试）
- 测试 88

### 第三轮（口径一致 + 单源化）
- P0 三统计端点路由级集成测试：insights/summary 支持 ?month=，editorEpisodes vs editors 逐人一致断言
- P1 集号识别抽离 episode_number.py（deliver/preview 共用，单源防漂移）
- P1 交付完整性统计 get_delivery_stats 补测试（目录计数/完成率/缓存）
- P0 提成插件单源化核查：配置已单源（都读 config.json），计算已有测试，backup 已 gitignore
- 测试 110

### 第四轮（文档同步）
- README/CONTEXT/ROADMAP 全量同步到 v3.3.0（版本徽章/文件结构/路线图/功能表）
- 确认缓存竞态、escHtml 统一等 P1 项已在历史提交完成

### 第五轮（工具链联动）
- P1 Excel 双向同步增强：sync_from_excel 支持差异检测（新增/修改/删除）+ apply_removals 精确同步模式
- P1 前端分集管理新增「🔄 精确同步」按钮 + 差异反馈展示
- P1 Premiere Pro CEP 插件（plugins/premiere-cep/）：连接工作台/读取项目/查找/标记剪辑完成/更新集数
- P1 后端新增 /api/project/<name>/set_episodes 接口 + /api/* CORS 支持（供 CEP 面板跨域调用）
- 测试 119

### 第六轮（BI 驾驶舱 + 风险预警 + 移动端增强）
- D1 桌面经营驾驶舱（static/js/bi.js）：KPI 卡（本月项目/完成/提成/按时交付率）+ 产能趋势 + 剪辑师排行 + 部门完成率 + 交付概览，聚合 insights/dashboard/commission/delivery_stats
- D2 桌面风险预警中心（static/js/risk.js + ⚠️ 新 Tab）：逾期交付 / 审核超时 / 今日与即将交付 / 待办提醒，聚合 audit/alerts + notifications，点击定位项目
- M2 移动端数据看板增强：数据 Tab 新增 产能趋势 / 部门统计 / 个人年度工作量卡片
- M4 移动端发起回传：成片预览加「📤 全部回传」+ 单文件回传，复用 /api/deliver_batch
- 测试 119

### 第七轮（本地剪辑工作流 + 扫描健壮性）
- 本地剪辑项目一键创建（backend/local_project.py）：按 episode_plan 定位"我负责集数"，在本地项目盘创建「序号-项目名」+ 复制模板结构，只拉负责集素材（扁平到 01原素材/第N集 剪辑师名）+ 整个剧本，异步进度条
- 制作部自动扫描（backend/project_scan_service.py）：daemon 线程每 10 分钟 scan_projects()，新建项目自动入库
- 递归扫描修复（scan.py）：_looks_like_project 编号正则放宽（H0189-11587《剧名》类）+ _CATEGORY_WORDS 移除"海外/国内"（误伤"国内版/海外版"项目名）
- 制作部项目自动获取集数：auto_detect_total_episodes 回退 production_path，接口返回明确原因（200+ok:false，不再 400）
- 前端弹窗统一：新增 showConfirm/进度/结果统一 modal（替代原生 confirm/alert）
- 测试 149

## 二、P0（下一步优先，会崩溃/数据错误/安全）
1. 前端 XSS 收尾：284 处内联 onclick/onchange 改事件委托 + data-* 属性（长期，需浏览器验证）
2. 提成 GUI 算法与主应用 commission_service 单源化：目前两边各有超额/缺集/组长组奖实现，
   建议 GUI 复用主应用纯函数或抽出共享模块（独立打包工具，风险较高，需专门轮次）

## 三、P1（规划期）
3. 拆分巨型文件（已有集号/交付统计测试保护，可谨慎推进）：
   - deliver.py(2022行) → delivery_core / delivery_revision / episode_counting / validation
   - app.py(1213行) → auth / sse / qa_result / service_control
   - enhanced_routes.py(1245行) → 按域拆 register_*
   - core.js(1670行) / fenji-assign.js(1217行) / wb-mobile.js(1185行) → 功能模块拆分
4. 前端引入轻量构建（Vite/esbuild）或至少按功能拆分 + 模块化，收敛 20+ 全局变量
5. loadProjects 的 N+1 episodes_status 请求优化（部分已做 episodes_status_batch）
6. 交付日期定时同步服务与手动导出写目标文件并发时的读一致性

## 四、P2（长期技术债）
7. DB 引入轻量迁移版本（schema_version），替代散落 ALTER TABLE
8. 统一运行时文件读写编码：deliver.py(gbk) vs detection.py(utf-8) 解码不一致
9. _parse_time_text 纯数字日期注释与实现不符
10. db.py _lock 误导性（未实际串行化）
11. 前端全局状态清理（_episodeStatusCache 等）

## 五、测试缺口（最痛）
- enhanced_routes.py / detection.py / app.py 仍几乎零覆盖
- 建议：detection 纯函数（黑帧/花屏/PSNR）、enhanced_routes 写文件占用分支、
  质检 None 兜底路径、分集 Excel 导出
