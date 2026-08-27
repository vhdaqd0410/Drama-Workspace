# 🎬 视频工作台 · Premiere Pro CEP 插件

在 Premiere Pro 内直接联动「视频工作台」：读取当前剪辑项目 → 在工作台查找匹配项目 → **标记剪辑完成（审核中）** → **更新当前集数**，无需切到浏览器。

## 功能

| 功能 | 说明 |
|---|---|
| 🔌 连接工作台 | 配置服务器地址 + API Key，检测连通性 |
| 🎬 读取 Premiere 项目 | 读取当前打开的项目名、序列列表、当前序列及集号 |
| 📁 在工作台查找 | 按 Premiere 项目名搜索工作台匹配项目 |
| ✂️ 标记剪辑完成 | 一键把工作台项目状态设为「审核中」 |
| 🔢 更新当前集数 | 从当前序列名解析集号，写入工作台 `current_episodes` |

## 目录结构

```
plugins/premiere-cep/
├── CSXS/manifest.xml   # CEP 面板清单（注册到 Premiere）
├── jsx/hostscript.jsx  # ExtendScript：读取 Premiere 项目/序列
├── index.html          # 面板 UI
├── js/panel.js         # 面板逻辑（工作台 API + JSX 桥接）
├── css/style.css       # 样式
└── install.bat         # 一键安装脚本
```

## 安装

1. **运行 `install.bat`**（双击），脚本会把插件复制到 `%APPDATA%\Adobe\CEP\extensions\com.workbench.premiere.cep\`，并可选写入 CEP 调试标志 `.debug`。
2. **开启 CEP 调试**（未签名的第三方插件必须）：确保文件 `%APPDATA%\Adobe\CEP\extensions\.debug` 存在且内容为：
   ```
   PlayerDebugMode=1
   ```
   （若 install.bat 已写入则可跳过）
3. **完全关闭并重启 Premiere Pro**。
4. 菜单 **窗口 → 扩展 → 视频工作台**，打开面板。

> 若面板不显示：确认 `.debug` 文件内容、Premiere 版本是否在 manifest 支持范围（PPRO 13.0+），或查看 Premiere 控制台（帮助→开发工具）。

## 使用

1. 在面板填入**工作台地址**（默认 `http://127.0.0.1:8089`）和 **API Key**（工作台设置页可查看/设置），点「检测连接」。
2. 面板自动读取当前 Premiere 项目（或点「读取项目」）。
3. 点「在工作台查找」匹配工作台项目。
4. 剪辑完成后点「标记剪辑完成」→ 工作台项目变「审核中」；点「更新当前集数」→ 同步当前序列集号。

## 后端依赖（已内置）

- `POST /api/project/<name>/custom_status` — 更新项目状态（已有）
- `POST /api/project/<name>/set_episodes` — 更新当前/总集数（**新增**，v3.4+）
- `GET /api/search?q=` — 搜索项目（已有）
- CORS 支持：后端已为 `/api/*` 开放跨域 + 预检（**新增**，v3.4+）

> ⚠️ 本机需先运行视频工作台后端（`start.bat`），且网络为 `127.0.0.1` 本机访问。
> 移动端/远程通过 Tailscale 访问时，把「服务器地址」改为电脑的 Tailscale IP（如 `http://100.68.53.62:8089`）。

## 开发调试

- 面板前端可在浏览器打开 `index.html` 调试（非 CEP 环境会自动用模拟 Premiere 数据）。
- JSX 改动后，在 Premiere 中重新加载面板即可。
- 面板与 JSX 通过 `csInterface.evalScript('__workbenchDispatch(...)')` 通信。

## 版本
- v1.0：连接 / 读取项目 / 查找 / 标记完成 / 更新集数。
