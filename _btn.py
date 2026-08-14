with open("static/js/episode.js", encoding="utf-8") as f:
    c = f.read()

# 交付预览按钮的条件状态
delivery_btn_snippet = """' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : ''"""

# 3 处修改预览按钮文本 — 每处后面追加交付预览按钮
# 第 1 处
old1 = """' : '') + '</div>';
          return { className: 'ep-missing-summary', html: html };"""
new1 = """' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';
          return { className: 'ep-missing-summary', html: html };"""
assert old1 in c, "old1 not found"
c = c.replace(old1, new1, 1)

# 第 2 处 — detailHint
old2 = """' : '') + '</div>';
      return {
        className: 'ep-missing-summary ok',"""
new2 = """' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';
      return {
        className: 'ep-missing-summary ok',"""
assert old2 in c, "old2 not found"
c = c.replace(old2, new2, 1)

# 第 3 处 — detailBtn（has-missing 最后一处）
old3 = """' : '') + '</div>';

    return {
      className: 'ep-missing-summary has-missing',"""
new3 = """' || customStatus === '交付中' || customStatus === '已交付' || customStatus === '已完成') ? '<button class="ep-detail-btn ep-deliv-btn" data-action="ep-delivery" data-project="' + htm(projectName) + '" style="margin-left:6px;background:#34c759;color:#fff">📦 交付预览</button>' : '') + '</div>';

    return {
      className: 'ep-missing-summary has-missing',"""
assert old3 in c, "old3 not found"
c = c.replace(old3, new3, 1)

with open("static/js/episode.js", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ episode.js 3处按钮添加完成")
