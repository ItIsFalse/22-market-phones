Set WshShell = CreateObject("WScript.Shell")

WshShell.CurrentDirectory = "D:\WEB\22-market"
WshShell.Run """D:\WEB\22-market\.venv\Scripts\python.exe"" ""D:\WEB\22-market\run.py""", 0, False