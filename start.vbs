Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir
WshShell.Run "python main.py", 0, False
WScript.Sleep 2500
WshShell.Run "http://127.0.0.1:8089/", 1, False
