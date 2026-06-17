Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

projectDir = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonw = "C:\Python313\pythonw.exe"
command = """" & pythonw & """ """ & projectDir & "\app.py"""

shell.CurrentDirectory = projectDir
shell.Run command, 0, False
