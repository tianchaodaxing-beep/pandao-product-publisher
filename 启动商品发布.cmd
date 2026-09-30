@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto failed
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m publisher serve
if errorlevel 1 goto failed
exit /b 0
:failed
echo 无法启动。请检查 Python 是否已安装，以及依赖安装时显示的错误。
pause
exit /b 1
