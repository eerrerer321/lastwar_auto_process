' Double-click this file to open the DailyWork GUI without any console window.
' It runs start_dailywork.bat hidden. If the startup check fails, run
' start_dailywork.bat directly to see the details.
Option Explicit

Dim shell, folder, exitCode
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
exitCode = shell.Run("cmd /c """"" & folder & "\start_dailywork.bat"" --hidden""", 0, True)
If exitCode <> 0 Then
    MsgBox "DailyWork could not start (Python or required packages may be missing)." & vbCrLf & _
           "Run start_dailywork.bat to see the details.", vbExclamation, "LastWar DailyWork"
End If
