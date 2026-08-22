# 移动端 wb-mobile.js 拆分方案（P1-B）

> 目标：把 `static/js/wb-mobile.js`（约 1093 行、42 个方法）按页面拆分为多个文件，提升可维护性。
> 状态：**方案已定，尚未执行**（因涉及大文件重构，风险高，建议在专门的重构轮次执行并完整回归测试）。

## 为什么拆
`wb-mobile.js` 单文件承载了手机端全部页面逻辑（首页/详情/数据/分集/待办），改动一处易碰全局。拆分后各文件职责单一。

## 拆分结构

```
static/js/
├── wb-mobile.js            # 基础骨架：mobile 对象 + 通用方法（init/load/render/switchTab/isMobile/工具）
├── wb-mobile-home.js       # 首页：renderHome/_renderHomeList/_projectCard/_statusBadge/setSearch/setStatus
├── wb-mobile-detail.js     # 项目详情 + 各预览：openDetail/loadEpisodeInfo/openChengPreview/openRevisePreview/
│                           #   openReviseFolder/openFenmiaozhenBtn/playVideo/saveStatus/doSync/openGroup/deliverVersion
├── wb-mobile-stats.js      # 数据页：renderStats
└── wb-mobile-fenji.js      # 分集 Tab：renderFenji 及所有 fj* 方法
```

## 挂载方式（关键）
当前 `mobile` 是**单一对象字面量**，所有方法在 `{ ... }` 内。拆分后：

1. **基础文件** `wb-mobile.js`：
   - 保留 `var mobile = { 通用方法 }`（对象字面量）
   - 末尾改为 `window.WB.mobile = mobile;`（不再一次性赋全部方法）
   - 删掉分集/详情/数据/首页的专有方法

2. **各页面文件**：用**挂载方式**扩展同一个 mobile 对象：
   ```js
   // wb-mobile-fenji.js
   (function(){
     var M = (window.WB && window.WB.mobile) || {};
     M.renderFenji = function(content){ ... };  // this 指向 M（mobile）
     M.fjAssign = function(){ ... };
     // ...
     window.WB = window.WB || {}; window.WB.mobile = M;
   })();
   ```
   方法内部用 `this.xxx()` 调用其他方法，`this` 仍指向 mobile，不受影响。

## 加载顺序（index.html）
```
wb-shared.js      → WB.escHtml / WB.api
fenji-core.js     → FenjiCore（分集工具）
wb-mobile.js      → 基础骨架（定义 WB.mobile）
wb-mobile-fenji.js
wb-mobile-home.js
wb-mobile-detail.js
wb-mobile-stats.js
```

## 执行步骤（建议专门轮次做）
1. 备份 `wb-mobile.js`
2. 用 Python 脚本精确提取各页面方法 → 生成新文件（挂载方式）
3. 在 `wb-mobile.js` 删除对应方法
4. 更新 `index.html` 脚本引用顺序
5. `node --check` 全部语法
6. **完整回归测试手机端所有页面**（首页/详情/数据/分集/待办/左滑/预览）
7. 通过后删除备份、提交

## 注意事项
- 方法间通过 `this` 相互调用，挂载后 `this` 上下文不变
- `_workflowOrder` 是 IIFE 内私有函数，拆分时需在需要的文件里重复定义或放到 fenji-core
- `openFjProjectPicker`/`fjPickerSearch` 等依赖 `_data`/`_fj` 状态，拆分后仍通过 `this` 访问 mobile 状态
- 拆分后务必重启 + 真机验证，防止回归
