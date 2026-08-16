Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
guiPath = dir & "\ai_commission_gui.py"

If Not fso.FileExists(guiPath) Then
    MsgBox "Cannot find: " & guiPath, 48, "Error"
    WScript.Quit 1
End If

' 优先 Python 3.13（已安装全部依赖），其次 PATH 中的 pythonw
py313 = "C:\Users\Admin\AppData\Local\Programs\Python\Python313\pythonw.exe"
If fso.FileExists(py313) Then
    pyPath = py313
Else
    pyPath = "pythonw.exe"
End If

cmd = """" & pyPath & """ """ & guiPath & """"
WshShell.Run cmd, 0, False
