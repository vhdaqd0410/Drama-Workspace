# 视频工作台 · 安卓手机端（WebView 壳）

通过 **Tailscale 内网组网** 让安卓手机访问电脑上的视频工作台，支持查看和操作（含同步/回传）。

## 原理
- 电脑和手机都已加入 Tailscale（电脑 IP `100.68.53.62`）。
- 本 App 用 WebView 加载 `http://100.68.53.62:8089/`。
- 后端已改为监听 `0.0.0.0`，API key 由后端在渲染页面时自动注入，App 无需处理 key。
- **不暴露公网**：仅 Tailscale 网络内的设备可访问。

## 一、环境准备（电脑，一次性）

你电脑目前**还没有** Android 开发环境，需要装一个 **Android Studio**（它会自带 JDK、Android SDK、Gradle）：

1. 下载 Android Studio：https://developer.android.com/studio
2. 安装时勾选 **Android SDK** 和 **Android Virtual Device（可不用）**，一路下一步。
3. 首次启动会下载 SDK 组件，需联网，等待完成。
4. 创建或打开一个项目时会要求设置 SDK 位置，用默认的 `C:\Users\<你>\AppData\Local\Android\Sdk` 即可。

## 二、编译 APK

1. 打开 Android Studio → `Open` → 选择 `mobile-app/WorkbenchMobile` 文件夹。
2. 首次打开会提示 **Gradle Sync**（自动下载 Gradle 依赖），点 **OK** 等它完成。
3. 顶部菜单 `Build → Build Bundle(s) / APK(s) → Build APK(s)`。
4. 编译完成弹出提示，APK 在 `app/build/outputs/apk/debug/app-debug.apk`。

> 也可用 USB 数据线连手机，点绿色 ▶ 直接运行到手机（需手机开「开发者选项 → USB 调试」）。

## 三、安装到手机

- 把 `app-debug.apk` 传到安卓手机（微信/QQ/数据线均可）。
- 手机允许「安装未知来源应用」，点击安装。
- 手机需**保持 Tailscale 已连接**（手机 Tailscale 里的「DNS unavailable」警告不影响 IP 访问，可忽略）。

## 四、使用

- 打开「视频工作台」App，自动加载 Tailscale 地址。
- **右上角三点菜单**：修改服务器地址 / 刷新 / 退出。
- 返回键：回退网页历史。
- 首次若打不开，确认手机浏览器能访问 `http://100.68.53.62:8089/`（能开则 App 也能）。

## 五、改服务器地址

App 内「修改服务器地址」可改为任意 Tailscale 地址或内网 IP。若电脑 Tailscale IP 变了，改这里即可（下次启动记忆该地址）。

## 目录结构
```
WorkbenchMobile/
├── build.gradle / settings.gradle / gradle.properties
└── app/
    ├── build.gradle
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/workbench/mobile/MainActivity.java   # WebView 壳核心
        └── res/
            ├── layout/activity_main.xml   # WebView + 进度条布局
            ├── values/themes.xml
            └── drawable/ic_launcher.xml   # 图标
```

## 常见问题
- **Gradle Sync 很慢**：首次需下载依赖，可换国内镜像（在 `build.gradle` 的 repositories 加阿里云镜像）。
- **SDK 版本报错**：项目用 compileSdk 34，如 SDK 没装 34，Android Studio 会提示安装，点同意即可。
- **手机打不开**：确认电脑工作台在运行 + 监听 0.0.0.0 + 手机 Tailscale 已连。
