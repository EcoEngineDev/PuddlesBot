# PowerShell script to start PuddlesBot with proper Unicode support
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
python main.py
