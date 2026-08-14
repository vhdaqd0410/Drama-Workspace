' 🎬 视频工作台 — 桌面版无黑窗启动器
' 双击本文件即可，不会弹出 CMD 黑窗口
Dim ws, appDir, cmd
Set ws = CreateObject("WScript.Shell")
appDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "pythonw """ & appDir & "\main_desktop.py"""
ws.Run cmd, 0, False
