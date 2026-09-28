Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
venv = folder & "\.venv\Scripts\pythonw.exe"
If fs.FileExists(venv) Then
    shell.Run Chr(34) & venv & Chr(34) & " " & Chr(34) & folder & "\desktop_ui.py" & Chr(34), 0, False
Else
    shell.Run "pythonw.exe " & Chr(34) & folder & "\desktop_ui.py" & Chr(34), 0, False
End If
