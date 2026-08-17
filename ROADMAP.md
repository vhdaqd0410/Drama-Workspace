# 视频工作台 · 下一步开发计划（ROADMAP）

> 基于 2026-08 代码评审（主代理 + 子代理双重核验）。已完成的修复见 v2.9.0 之后提交。
> 优先级：P0=崩溃/数据错误/安全；P1=重要改进；P2=长期技术债。

## 一、已完成（本轮）
- P0 三统计端点统一口径（compute_insights_summary），修 monthCompleted 误用 delivered_date
- P0 统一分集解析器（fenji_parser.py），消除三处重复漂移
- P0 前端 onclick XSS（jsq 统一转义，28 处）
- P0 产能趋势 1~5 月崩溃（backfill_months）
- P1 限制任意路径写文件（export_excel / save_to_folder）
- P1 删除 index() boot_data 死代码（白扫 NAS）
- P1 关键 except 补日志 + CONTEXT.md 口径同步
- 测试 39→49

## 二、P0（下一步优先，会崩溃/数据错误/安全）
1. 提成插件单源化：plugins/commission 与独立工具重复，且 backup/ 有 50 个 .bak_*；
   清理快照，消除双份漂移（本次 GBK bug 即由此引起）
2. 前端 XSS 收尾：改用事件委托 + data-* 属性逐步替换剩余内联 onclick（长期）
3. 补路由级集成测试：三个统计端点对同一批数据断言口径一致（当前只测了纯函数层）

## 三、P1（规划期）
4. 拆分巨型文件：
   - deliver.py(2093行) → delivery_core / delivery_revision / episode_counting / validation
   - app.py(1258行) → auth / sse / qa_result / service_control
   - enhanced_routes.py(1316行) → 按域拆 register_*
   - core.js(1280行) / fenji-assign.js(1273行) → 功能模块拆分
5. 前端引入轻量构建（Vite/esbuild）或至少按功能拆分 + 模块化，收敛 20+ 全局变量
6. 修 _output_dir_cache 竞态（reload_sync_engine 加锁）+ VideoInfoCache 无锁
7. 统一 escHtml/htm（三处定义不一致）+ _isShell 判断去重
8. loadProjects 的 N+1 episodes_status 请求优化

## 四、P2（长期技术债）
9. DB 引入轻量迁移版本（schema_version），替代散落 ALTER TABLE
10. 统一编码：deliver.py(gbk) vs detection.py(utf-8) 解码不一致
11. _parse_time_text 纯数字日期注释与实现不符
12. db.py _lock 误导性（未实际串行化）
13. 前端全局状态清理（_episodeStatusCache 等）

## 五、测试缺口（最痛）
- deliver.py / enhanced_routes.py / detection.py / app.py 及三统计端点几乎零覆盖
- 建议：路由级集成测试（三端点口径）、deliver 批量回传、detection 纯函数
