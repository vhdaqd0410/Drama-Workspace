@echo off
chcp 65001 >nul
REM ============================================================
REM  视频工作台 · Premiere Pro CEP 插件一键安装脚本
REM  把插件复制到 Adobe CEP 扩展目录，然后在 Premiere 中启用
REM ============================================================
setlocal

set "SRC=%~dp0"
set "TARGET=%APPDATA%\Adobe\CEP\extensions\com.workbench.premiere.cep"

echo.
echo ============================================================
echo   安装 视频工作台 CEP 插件
echo ============================================================
echo   源目录: %SRC%
echo   目标目录: %TARGET%
echo.

REM 1. 创建目标目录
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
if not exist "%TARGET%" (
  echo [错误] 无法创建目标目录: %TARGET%
  echo 请检查 Adobe CEP 扩展目录是否可写。
  pause
  exit /b 1
)

REM 2. 复制文件（排除脚本自身）
echo 正在复制插件文件...
xcopy "%SRC%CSXS" "%TARGET%\CSXS\" /E /I /Y /Q >nul
xcopy "%SRC%jsx" "%TARGET%\jsx\" /E /I /Y /Q >nul
xcopy "%SRC%js" "%TARGET%\js\" /E /I /Y /Q >nul
xcopy "%SRC%css" "%TARGET%\css\" /E /I /Y /Q >nul
copy /Y "%SRC%index.html" "%TARGET%\index.html" >nul

echo.
echo 已复制到: %TARGET%
echo.
echo  下一步：
echo    1. 若未开启 CEP 调试，需创建/编辑 CEP 调试标志文件
echo       %APPDATA%\Adobe\CEP\extensions\.debug
echo       内容写: PlayerDebugMode=1  （否则插件不显示，见 README）
echo    2. 完全关闭并重启 Premiere Pro
echo    3. 菜单: 窗口(Window) - 扩展(Extensions) - 视频工作台
echo.
echo 是否现在写入 CEP 调试标志（.debug 文件）？(Y/N)
set /p "YN="
if /I "%YN%"=="Y" (
  echo PlayerDebugMode=1 > "%APPDATA%\Adobe\CEP\extensions\.debug"
  echo 已写入调试标志。
)
echo.
echo 安装完成！请重启 Premiere Pro 后从 窗口-扩展 打开面板。
pause
