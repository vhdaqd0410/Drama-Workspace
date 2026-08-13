# -*- coding: utf-8 -*-
"""视频质检工具 — HTML 报告模板（CSS 样式 & HTML 结构）"""

REPORT_CSS = r"""
  :root {
    --bg: #f7f8fa;
    --card: #ffffff;
    --text: #1f2937;
    --text2: #6b7280;
    --border: #e5e7eb;
    --primary: #3b82f6;
    --success: #22c55e;
    --warning: #f59e0b;
    --danger: #ef4444;
    --shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
  .container { max-width: 1200px; margin: 0 auto; }
  h1 { color: var(--text); border-bottom: 3px solid var(--primary); padding-bottom: 12px; margin-bottom: 24px; }
  h2 { color: var(--text); margin-top: 32px; padding-left: 12px; border-left: 4px solid var(--primary); }
  .meta { color: var(--text2); font-size: 14px; margin-bottom: 16px; }
  .summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: var(--card); border-radius: 8px; padding: 16px; box-shadow: var(--shadow); border-left: 4px solid var(--primary); }
  .stat-card.success { border-left-color: var(--success); }
  .stat-card.warning { border-left-color: var(--warning); }
  .stat-card.danger { border-left-color: var(--danger); }
  .stat-value { font-size: 28px; font-weight: 700; color: var(--text); }
  .stat-label { color: var(--text2); font-size: 13px; margin-top: 4px; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; overflow: hidden; box-shadow: var(--shadow); margin-bottom: 24px; }
  thead { background: #f3f4f6; }
  th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); font-size: 14px; }
  th { font-weight: 600; color: var(--text); }
  td { color: var(--text); }
  tr:hover { background: #f9fafb; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .badge-success { background: #d1fae5; color: #065f46; }
  .badge-warning { background: #fef3c7; color: #92400e; }
  .badge-danger { background: #fee2e2; color: #991b1b; }
  .conclusion { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); border-left: 4px solid var(--success); padding: 16px 20px; border-radius: 8px; margin-bottom: 16px; }
  .conclusion.warning { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-left-color: var(--warning); }
  .conclusion.danger { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); border-left-color: var(--danger); }
  .conclusion strong { color: #064e3b; }
  .note { background: #eff6ff; border-left: 3px solid var(--primary); padding: 12px 16px; border-radius: 4px; margin: 12px 0; font-size: 14px; color: var(--text); }
  .video-num { font-family: monospace; font-weight: 600; }
  details { margin-bottom: 8px; }
  summary { cursor: pointer; padding: 10px 12px; background: #f9fafb; border-radius: 6px; font-weight: 500; }
  summary:hover { background: #f3f4f6; }
"""
