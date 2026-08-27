Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir
' 桌面版启动（无浏览器地址栏）；网页版请用 start_browser.bat
WshShell.Run "pythonw """ & strDir & "\main_desktop.py""", 0, False
